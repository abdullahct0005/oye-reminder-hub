import streamlit as st
import pandas as pd
import re
from io import BytesIO
from urllib.parse import quote
from datetime import datetime
import streamlit.components.v1 as components

# ============================================================
# OYE COURSE REMINDER HUB
# One reusable WhatsApp tab + batches of 10
# IMPORTANT:
# Regular WhatsApp Web cannot hold 10 different chat drafts
# simultaneously in one tab. One tab can display only one chat.
# This app keeps 10 OECs in the current batch and reuses ONE
# WhatsApp tab for whichever OEC you choose.
# ============================================================

st.set_page_config(
    page_title="OYE Course Reminder Hub",
    page_icon="📚",
    layout="wide"
)

BATCH_SIZE = 10

REQUIRED_COLUMNS = [
    "employee's name",
    "Mob No",
    "Trainer Name"
]

FIXED_COLUMNS = {
    "employee's name",
    "Mob No",
    "Store",
    "duties",
    "superior",
    "Entry date",
    "Zone",
    "Location",
    "Active status",
    "Trainer Name",
    "Total Course pending",
    "Total Course Completed",
    "Total Course Enrolled",
    "TYPE"
}


# ============================================================
# HELPERS
# ============================================================

def clean_text(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def clean_phone(value):
    """
    Returns:
        phone_with_country_code, is_valid
    """
    if pd.isna(value):
        return "", False

    value = str(value).strip()
    value = re.sub(r"\.0$", "", value)
    digits = re.sub(r"\D", "", value)

    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]

    if len(digits) == 10 and digits[0] in "6789":
        return "91" + digits, True

    return "", False


def split_name_emp(value):
    """
    Example:
    Abdullah C T-5005805

    Returns:
    Abdullah C T
    5005805
    """
    value = clean_text(value)

    match = re.search(r"-(\d{5,})$", value)

    if match:
        return value[:match.start()].strip(), match.group(1)

    return value, ""


def get_course_columns(df):
    """
    Any column not in the fixed OYE columns is treated as a course.
    Therefore newly added courses are detected automatically when
    the new Excel file is uploaded.
    """
    return [
        column
        for column in df.columns
        if column not in FIXED_COLUMNS
    ]


def get_course_status(value):
    value = clean_text(value)
    return value if value else "Not started"


def get_campaign_status(value):
    return (
        "Completed"
        if clean_text(value).lower() == "completed"
        else "Pending"
    )


def build_message(
    name,
    course,
    status,
    reminder_level,
    custom_template=""
):
    """
    Custom placeholders:
    {name}
    {course}
    {status}

    If a custom template is used, placeholders are replaced
    automatically for every OEC and every selected course.
    """

    name = clean_text(name)
    course = clean_text(course)
    status = clean_text(status)

    if custom_template.strip():
        return (
            custom_template
            .replace("{name}", name)
            .replace("{course}", course)
            .replace("{status}", status)
        )

    if reminder_level == "First Reminder":
        return (
            f"Hi {name},\n\n"
            f"Your *{course}* course on OYE is currently showing as "
            f"*{status}*.\n\n"
            f"Please complete the course as soon as possible. "
            f"This is mandatory."
        )

    if reminder_level == "Second Reminder":
        return (
            f"Hi {name},\n\n"
            f"This is a reminder that your *{course}* course is still "
            f"showing as *{status}* on OYE.\n\n"
            f"Please complete the mandatory course immediately."
        )

    return (
        f"Hi {name},\n\n"
        f"URGENT REMINDER:\n\n"
        f"Your *{course}* course is still pending on OYE "
        f"(Status: *{status}*).\n\n"
        f"Please complete it immediately. "
        f"This is mandatory."
    )


def make_whatsapp_web_url(phone, message):
    return (
        "https://web.whatsapp.com/send"
        f"?phone={phone}"
        f"&text={quote(message)}"
    )


def make_mobile_whatsapp_url(phone, message):
    return (
        "https://api.whatsapp.com/send"
        f"?phone={phone}"
        f"&text={quote(message)}"
    )


def open_whatsapp_in_reusable_tab(url, label, key):
    """
    Opens/reuses ONE browser window/tab with the fixed name
    oye_whatsapp_window.

    The important part is window.open(url, 'oye_whatsapp_window')
    instead of target=_blank.

    Every OEC button calls the same named window.
    """
    html = f"""
    <button
        id="btn-{key}"
        style="
            width:100%;
            padding:12px 16px;
            border-radius:8px;
            border:1px solid #25D366;
            background:#25D366;
            color:white;
            font-weight:700;
            font-size:15px;
            cursor:pointer;
        "
    >
        {label}
    </button>

    <script>
    const btn = document.getElementById("btn-{key}");
    btn.addEventListener("click", function() {{
        const url = {url!r};
        const wa = window.open(
            url,
            "oye_whatsapp_window",
            "noopener=no"
        );

        if (wa) {{
            wa.focus();
        }} else {{
            window.location.href = url;
        }}
    }});
    </script>
    """

    components.html(
        html,
        height=55
    )


@st.cache_data(show_spinner=False)
def load_report(file_bytes):
    return pd.read_excel(BytesIO(file_bytes))


def reset_campaign(campaign_key):
    st.session_state.campaign_state = {
        "campaign_key": campaign_key,
        "batch_number": 0,
        "sent_ids": set(),
        "started": False,
        "started_at": None
    }


# ============================================================
# SESSION STATE
# ============================================================

if "campaign_state" not in st.session_state:
    reset_campaign(None)


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:
    st.header("Admin / Report")

    uploaded_file = st.file_uploader(
        "Upload latest OYE Excel",
        type=["xlsx", "xls"]
    )

    st.caption(
        "Upload the newest OYE report whenever completion "
        "status changes."
    )

    st.divider()

    st.header("How trainers use it")

    st.markdown(
        """
        1. Upload latest report  
        2. Select your trainer name  
        3. Select course  
        4. Start campaign  
        5. View 10 OECs at a time  
        6. Open an OEC's personalized WhatsApp draft  
        7. Manually click Send in WhatsApp Web  
        8. Return here and mark the OEC as sent  
        9. Move to the next OEC or next batch  
        """
    )

    st.divider()

    st.caption(
        "One reusable WhatsApp Web tab is used for all OECs."
    )


# ============================================================
# HEADER
# ============================================================

st.title("OYE Course Reminder Hub")

st.caption(
    "Upload OYE report • Select trainer • Select course • "
    "Send personalized WhatsApp reminders in batches of 10"
)


# ============================================================
# NO FILE
# ============================================================

if uploaded_file is None:
    st.info("Upload the latest OYE Excel report to start.")
    st.stop()


# ============================================================
# LOAD EXCEL
# ============================================================

try:
    raw = load_report(uploaded_file.getvalue())

except Exception as error:
    st.error(
        f"Could not read the Excel file: {error}"
    )
    st.stop()


# ============================================================
# VALIDATE COLUMNS
# ============================================================

missing_columns = [
    column
    for column in REQUIRED_COLUMNS
    if column not in raw.columns
]

if missing_columns:
    st.error(
        "Missing required columns: "
        + ", ".join(missing_columns)
    )
    st.stop()


# ============================================================
# TRAINERS AND COURSES
# ============================================================

courses = get_course_columns(raw)

trainers = sorted(
    raw["Trainer Name"]
    .dropna()
    .astype(str)
    .str.strip()
    .loc[lambda s: s != ""]
    .unique()
)

if not courses:
    st.error(
        "No course columns were detected in this Excel file."
    )
    st.stop()

if not trainers:
    st.error(
        "No trainer names were found."
    )
    st.stop()


# ============================================================
# SETTINGS
# ============================================================

col1, col2, col3 = st.columns(3)

with col1:
    trainer = st.selectbox(
        "Select Your Trainer Name",
        trainers
    )

with col2:
    course = st.selectbox(
        "Select Course",
        courses
    )

with col3:
    reminder_level = st.selectbox(
        "Reminder Type",
        [
            "First Reminder",
            "Second Reminder",
            "Final / Urgent Reminder"
        ]
    )


# ============================================================
# CUSTOM MESSAGE
# ============================================================

custom_template = st.text_area(
    "Optional Custom Message Template",
    placeholder=(
        "Example:\n\n"
        "Hi {name},\n\n"
        "Your *{course}* course status is *{status}*. "
        "Please complete it today."
    ),
    height=130
)

st.caption(
    "Placeholders are automatic: {name}, {course}, {status}. "
    "You do not need to type the OEC name or course manually "
    "for every message."
)


# ============================================================
# FILTER TRAINER DATA
# ============================================================

data = raw[
    raw["Trainer Name"]
    .astype(str)
    .str.strip()
    .eq(trainer)
].copy()

if data.empty:
    st.warning(
        "No OECs were found for the selected trainer."
    )
    st.stop()


# ============================================================
# NAME AND EMPLOYEE ID
# ============================================================

name_employee = data["employee's name"].apply(
    lambda value: pd.Series(split_name_emp(value))
)

name_employee.columns = [
    "OEC Name",
    "Employee ID"
]

data = pd.concat(
    [
        data.reset_index(drop=True),
        name_employee.reset_index(drop=True)
    ],
    axis=1
)


# ============================================================
# PHONE VALIDATION
# ============================================================

phone_result = data["Mob No"].apply(clean_phone)

data["WhatsApp Phone"] = phone_result.apply(
    lambda result: result[0]
)

data["Valid Number"] = phone_result.apply(
    lambda result: result[1]
)

data["Number Status"] = data["Valid Number"].apply(
    lambda valid:
    "Number Updated"
    if valid
    else "Number Not Updated in System"
)


# ============================================================
# COURSE STATUS
# ============================================================

data["Course Status"] = data[course].apply(
    get_course_status
)

data["Campaign Status"] = data[
    "Course Status"
].apply(
    get_campaign_status
)


# ============================================================
# PERSONALIZED MESSAGE
# ============================================================

data["Reminder Message"] = data.apply(
    lambda row: build_message(
        row["OEC Name"],
        course,
        row["Course Status"],
        reminder_level,
        custom_template
    ),
    axis=1
)


# ============================================================
# WHATSAPP LINKS
# ============================================================

data["WhatsApp Web Link"] = data.apply(
    lambda row:
    make_whatsapp_web_url(
        row["WhatsApp Phone"],
        row["Reminder Message"]
    )
    if row["Valid Number"]
    else "",
    axis=1
)

data["WhatsApp Mobile Link"] = data.apply(
    lambda row:
    make_mobile_whatsapp_url(
        row["WhatsApp Phone"],
        row["Reminder Message"]
    )
    if row["Valid Number"]
    else "",
    axis=1
)


# ============================================================
# UNIQUE ID
# ============================================================

data["Unique ID"] = data.apply(
    lambda row:
    f"{row['Employee ID']}|"
    f"{row['OEC Name']}|"
    f"{row['WhatsApp Phone']}",
    axis=1
)


# ============================================================
# PENDING / COMPLETED
# ============================================================

pending = (
    data[
        data["Campaign Status"] == "Pending"
    ]
    .copy()
    .reset_index(drop=True)
)

completed = (
    data[
        data["Campaign Status"] == "Completed"
    ]
    .copy()
    .reset_index(drop=True)
)


# ============================================================
# CAMPAIGN KEY
# Custom template is included so changing it resets the campaign
# ============================================================

campaign_key = (
    f"{uploaded_file.name}|"
    f"{uploaded_file.size}|"
    f"{trainer}|"
    f"{course}|"
    f"{reminder_level}|"
    f"{custom_template}|"
    f"{len(pending)}"
)

state = st.session_state.campaign_state

if state["campaign_key"] != campaign_key:
    reset_campaign(campaign_key)
    state = st.session_state.campaign_state


# ============================================================
# SUMMARY
# ============================================================

st.divider()

s1, s2, s3, s4 = st.columns(4)

s1.metric("My Total OECs", len(data))
s2.metric("Pending", len(pending))
s3.metric("Completed", len(completed))
s4.metric(
    "Completion %",
    f"{(len(completed) / len(data) * 100):.1f}%"
    if len(data)
    else "0.0%"
)

if pending.empty:
    st.success(
        "All OECs in the selected trainer/course are completed."
    )
    st.stop()


# ============================================================
# START CAMPAIGN
# ============================================================

st.divider()

top1, top2, top3 = st.columns([1.3, 1, 2])

with top1:
    if not state["started"]:
        if st.button(
            "Start Campaign",
            type="primary",
            use_container_width=True
        ):
            state["started"] = True
            state["started_at"] = (
                datetime.now()
                .strftime("%d-%m-%Y %I:%M %p")
            )
            st.rerun()
    else:
        st.success("Campaign Active")

with top2:
    st.metric(
        "Marked Sent",
        len(state["sent_ids"])
    )

with top3:
    remaining = max(
        0,
        len(pending) - len(state["sent_ids"])
    )

    st.metric(
        "Remaining",
        remaining
    )

    if state["started_at"]:
        st.caption(
            f"Started: {state['started_at']}"
        )

if not state["started"]:
    st.info(
        "Click Start Campaign to begin the batch."
    )
    st.stop()


# ============================================================
# BATCH CALCULATION
# ============================================================

total_batches = (
    len(pending) + BATCH_SIZE - 1
) // BATCH_SIZE

current_batch_number = min(
    state["batch_number"],
    total_batches - 1
)

state["batch_number"] = current_batch_number

start_index = current_batch_number * BATCH_SIZE
end_index = min(
    start_index + BATCH_SIZE,
    len(pending)
)

batch = pending.iloc[
    start_index:end_index
].copy()


# ============================================================
# BATCH NAVIGATION
# ============================================================

st.divider()

nav1, nav2, nav3 = st.columns([1, 2, 1])

with nav1:
    if st.button(
        "← Previous Batch",
        disabled=(current_batch_number == 0),
        use_container_width=True
    ):
        state["batch_number"] -= 1
        st.rerun()

with nav2:
    st.markdown(
        f"""
        <div style="
            text-align:center;
            padding-top:10px;
            font-size:18px;
            font-weight:700;
        ">
            Batch {current_batch_number + 1} of {total_batches}
            • Showing {len(batch)} OECs
        </div>
        """,
        unsafe_allow_html=True
    )

with nav3:
    if st.button(
        "Next Batch →",
        disabled=(
            current_batch_number
            >= total_batches - 1
        ),
        use_container_width=True
    ):
        state["batch_number"] += 1
        st.rerun()


# ============================================================
# CURRENT BATCH
# ============================================================

st.divider()

st.subheader(
    f"Current Batch – {len(batch)} OECs"
)

st.info(
    "This batch contains 10 personalized messages. "
    "Click any OEC's WhatsApp button and the SAME reusable "
    "WhatsApp Web tab will navigate to that OEC's draft. "
    "Regular WhatsApp Web can show only one active chat/draft "
    "inside one tab, so the 10 chats are handled sequentially. "
    "You manually click Send in WhatsApp."
)


# ============================================================
# SHOW OECs
# ============================================================

for position, (_, row) in enumerate(
    batch.iterrows(),
    start=start_index + 1
):

    oec_id = row["Unique ID"]

    with st.container(border=True):

        left, middle, right = st.columns(
            [1.3, 2, 1.3]
        )

        with left:
            st.markdown(
                f"### {position}. {row['OEC Name']}"
            )

            st.caption(
                "Employee ID: "
                + (
                    row["Employee ID"]
                    if row["Employee ID"]
                    else "Not available"
                )
            )

        with middle:
            st.write(
                f"**Store:** {row.get('Store', '')}"
            )

            st.write(
                f"**Course Status:** "
                f"{row['Course Status']}"
            )

            if "TYPE" in row.index:
                st.write(
                    f"**Type:** {row.get('TYPE', '')}"
                )

        with right:
            if row["Valid Number"]:
                st.success("Number Updated")

                st.caption(
                    row["WhatsApp Phone"]
                )
            else:
                st.error(
                    "Number Not Updated in System"
                )

                original_number = clean_text(
                    row["Mob No"]
                )

                if original_number:
                    st.caption(
                        f"Current value: {original_number}"
                    )

        with st.expander(
            "View personalized message"
        ):
            st.text_area(
                "Message",
                value=row["Reminder Message"],
                height=150,
                disabled=True,
                key=f"message_{campaign_key}_{oec_id}"
            )

        if row["Valid Number"]:

            open_whatsapp_in_reusable_tab(
                row["WhatsApp Web Link"],
                "Open / Reuse WhatsApp Web Draft",
                re.sub(
                    r"[^A-Za-z0-9_]",
                    "_",
                    f"{campaign_key}_{oec_id}"
                )[:100]
            )

            st.caption(
                "This uses the same named browser window "
                "`oye_whatsapp_window` for every OEC."
            )

        else:
            st.warning(
                "A valid mobile number is not available, "
                "so this OEC cannot be opened in WhatsApp."
            )

        sent_col, status_col = st.columns(2)

        with sent_col:
            if oec_id in state["sent_ids"]:
                st.success("Marked as Sent")
            else:
                if st.button(
                    "Mark as Sent",
                    key=f"sent_{campaign_key}_{oec_id}",
                    use_container_width=True
                ):
                    state["sent_ids"].add(oec_id)
                    st.rerun()

        with status_col:
            if not row["Valid Number"]:
                st.warning("Number unavailable")
            elif oec_id in state["sent_ids"]:
                st.success("Session Status: Sent")
            else:
                st.info("Session Status: Pending")


# ============================================================
# BOTTOM NAVIGATION
# ============================================================

st.divider()

bottom1, bottom2, bottom3 = st.columns(
    [1, 2, 1]
)

with bottom1:
    if st.button(
        "← Previous Batch ",
        disabled=(current_batch_number == 0),
        use_container_width=True
    ):
        state["batch_number"] -= 1
        st.rerun()

with bottom2:
    st.markdown(
        f"""
        <div style="
            text-align:center;
            padding-top:10px;
            font-weight:700;
        ">
            Batch {current_batch_number + 1}
            of {total_batches}
        </div>
        """,
        unsafe_allow_html=True
    )

with bottom3:
    if st.button(
        "Next Batch → ",
        disabled=(
            current_batch_number
            >= total_batches - 1
        ),
        use_container_width=True
    ):
        state["batch_number"] += 1
        st.rerun()


# ============================================================
# RESET
# ============================================================

st.divider()

if st.button(
    "Reset My Campaign Session",
    use_container_width=True
):
    reset_campaign(campaign_key)
    st.rerun()


# ============================================================
# PENDING QUEUE
# ============================================================

st.divider()

st.subheader("My Pending Queue")

queue = pending.copy()

queue["Session Status"] = queue[
    "Unique ID"
].apply(
    lambda value:
    "Marked Sent"
    if value in state["sent_ids"]
    else "Pending Send"
)

display_columns = [
    "OEC Name",
    "Employee ID",
    "Number Status",
    "WhatsApp Phone",
    "Store",
    "TYPE",
    "Course Status",
    "Session Status"
]

available_columns = [
    column
    for column in display_columns
    if column in queue.columns
]

st.dataframe(
    queue[available_columns],
    use_container_width=True,
    hide_index=True,
    height=400
)

download_data = (
    queue[available_columns]
    .to_csv(index=False)
    .encode("utf-8-sig")
)

st.download_button(
    "Download My Campaign Queue (CSV)",
    data=download_data,
    file_name=(
        f"OYE_{trainer.replace(' ', '_')}_"
        f"{course.replace(' ', '_')}.csv"
    ),
    mime="text/csv",
    use_container_width=True
)

st.divider()

st.caption(
    "OYE Reminder Hub • Messages are not sent automatically. "
    "Each OEC receives a personalized draft with the selected "
    "course and their name. The trainer manually clicks Send "
    "in WhatsApp Web."
)
