import streamlit as st
import pandas as pd
import re
from urllib.parse import quote
from datetime import datetime
from io import BytesIO
import streamlit.components.v1 as components


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="OYE Course Reminder Hub",
    page_icon="📚",
    layout="wide"
)


# ============================================================
# SETTINGS
# ============================================================

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
# FUNCTIONS
# ============================================================

def normalise_column_name(column):
    """Remove unwanted spaces from column names."""
    return str(column).strip()


def clean_phone(value):
    """
    Clean Indian mobile number.

    Returns:
    10 digit phone number
    91XXXXXXXXXX
    or None if number is missing/invalid
    """

    if pd.isna(value):
        return None

    value = str(value).strip()

    if value == "":
        return None

    # Remove .0 caused by Excel
    value = value.replace(".0", "")

    digits = re.sub(r"\D", "", value)

    # 10 digit Indian mobile number
    if len(digits) == 10:
        return "91" + digits

    # Already has country code
    if len(digits) == 12 and digits.startswith("91"):
        return digits

    # Sometimes Excel/report contains 11+ digit variations
    if len(digits) == 11 and digits.startswith("0"):
        return "91" + digits[-10:]

    return None


def split_name_emp(value):
    """
    Split:
    Abdullah C T-5005805

    Into:
    Abdullah C T
    5005805
    """

    if pd.isna(value):
        return "", ""

    text = str(value).strip()

    match = re.search(r"-(\d{5,})$", text)

    if match:
        name = text[:match.start()].strip()
        employee_id = match.group(1)
        return name, employee_id

    return text, ""


def course_columns(df):
    """Detect all OYE course columns."""

    return [
        column
        for column in df.columns
        if column not in FIXED_COLUMNS
    ]


def status_class(value):
    """Classify OYE course status."""

    status = str(value).strip().lower()

    completed_statuses = {
        "completed",
        "complete"
    }

    if status in completed_statuses:
        return "Completed"

    return "Pending"


def build_message(
    name,
    course,
    status,
    reminder_level,
    custom_text=""
):
    """Create personalized WhatsApp message."""

    name = str(name).strip()
    course = str(course).strip()
    status = str(status).strip()

    if custom_text.strip():

        message = custom_text

        message = message.replace(
            "{name}",
            name
        )

        message = message.replace(
            "{course}",
            course
        )

        message = message.replace(
            "{status}",
            status
        )

        return message

    if reminder_level == "First Reminder":

        return (
            f"Hi {name},\n\n"
            f"Your *{course}* course on OYE is currently "
            f"showing as *{status}*.\n\n"
            f"Please complete the course as soon as possible. "
            f"This is mandatory."
        )

    if reminder_level == "Second Reminder":

        return (
            f"Hi {name},\n\n"
            f"This is a reminder that your *{course}* course "
            f"is still showing as *{status}* on OYE.\n\n"
            f"Please complete the mandatory course immediately."
        )

    return (
        f"Hi {name},\n\n"
        f"*URGENT REMINDER*\n\n"
        f"Your *{course}* course is still pending on OYE.\n\n"
        f"Please complete it immediately."
    )


def open_whatsapp_same_tab(phone, message):
    """
    Open WhatsApp chat in ONE reusable WhatsApp tab.

    The browser window/tab name is:
    oye_whatsapp

    So clicking the next OEC should reuse the same WhatsApp tab.
    """

    url = (
        f"https://web.whatsapp.com/send?"
        f"phone={phone}"
        f"&text={quote(message)}"
    )

    components.html(
        f"""
        <script>
        window.open(
            "{url}",
            "oye_whatsapp"
        );
        </script>
        """,
        height=0,
        width=0
    )


@st.cache_data(show_spinner=False)
def load_report(file_bytes):
    """
    Read uploaded Excel safely.

    BytesIO fixes:
    Expected file path name or file-like object,
    got <class 'bytes'>
    """

    return pd.read_excel(
        BytesIO(file_bytes)
    )


# ============================================================
# SESSION STATE
# ============================================================

if "campaign_state" not in st.session_state:

    st.session_state.campaign_state = {
        "key": None,
        "sent": set(),
        "batch": 0,
        "started": False,
        "started_at": None
    }


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.header("Admin / Report")

    uploaded = st.file_uploader(
        "Upload latest OYE Excel",
        type=["xlsx", "xls"]
    )

    st.caption(
        "Upload the newest report whenever "
        "OYE completion status changes."
    )

    st.divider()

    st.header("How trainers use it")

    st.markdown(
        f"""
1. Upload latest report
2. Select your trainer name
3. Select course
4. Start campaign
5. View {BATCH_SIZE} OECs at a time
6. Open personalized WhatsApp draft
7. Manually click Send
8. Mark OEC as sent
9. Move to next batch
"""
    )

    st.divider()

    st.subheader("WhatsApp Notice")

    st.caption(
        "Messages are sent manually from the WhatsApp "
        "account currently logged in on WhatsApp Web."
    )


# ============================================================
# HEADER
# ============================================================

st.title("OYE Course Reminder Hub")

st.caption(
    "Shared trainer dashboard • Upload OYE report • "
    "Select trainer • Send personalized WhatsApp reminders "
    f"in batches of {BATCH_SIZE}"
)


# ============================================================
# UPLOAD VALIDATION
# ============================================================

if not uploaded:

    st.info(
        "Upload the latest OYE Excel report from "
        "the left panel to start."
    )

    st.stop()


try:

    raw = load_report(
        uploaded.getvalue()
    )

    raw.columns = [
        normalise_column_name(column)
        for column in raw.columns
    ]

except Exception as e:

    st.error(
        f"Could not read the Excel file: {e}"
    )

    st.stop()


# ============================================================
# REQUIRED COLUMNS
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
# COURSE DETECTION
# ============================================================

courses = course_columns(raw)

if not courses:

    st.error(
        "No OYE course columns were detected."
    )

    st.stop()


# ============================================================
# TRAINERS
# ============================================================

trainers = sorted(
    raw["Trainer Name"]
    .dropna()
    .astype(str)
    .str.strip()
    .unique()
)


# ============================================================
# SETTINGS
# ============================================================

a, b, c = st.columns(3)

with a:

    trainer = st.selectbox(
        "Select Your Trainer Name",
        trainers
    )


with b:

    course = st.selectbox(
        "Select Course",
        courses
    )


with c:

    reminder_level = st.selectbox(
        "Reminder Type",
        [
            "First Reminder",
            "Second Reminder",
            "Final / Urgent Reminder"
        ]
    )


custom_template = st.text_area(
    "Optional custom message template",
    placeholder=(
        "Example:\n"
        "Hi {name}, your {course} course is {status}. "
        "Please complete it today.\n\n"
        "Available: {name}, {course}, {status}"
    ),
    height=120
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


# ============================================================
# PROCESS OEC DETAILS
# ============================================================

data[[
    "OEC Name",
    "Employee ID"
]] = data[
    "employee's name"
].apply(
    lambda x: pd.Series(
        split_name_emp(x)
    )
)


# ============================================================
# PHONE VALIDATION
# ============================================================

data["WhatsApp Phone"] = data[
    "Mob No"
].apply(
    clean_phone
)


data["Phone Status"] = data[
    "WhatsApp Phone"
].apply(
    lambda x:
    "Number Updated"
    if x
    else "Number not updated in the system"
)


# ============================================================
# COURSE STATUS
# ============================================================

data["Course Status"] = (
    data[course]
    .fillna("Not started")
    .astype(str)
    .str.strip()
)


data["Campaign Status"] = data[
    "Course Status"
].apply(
    status_class
)


# ============================================================
# PERSONALIZED MESSAGE
# ============================================================

data["Reminder Message"] = data.apply(
    lambda row: build_message(
        name=row["OEC Name"],
        course=course,
        status=row["Course Status"],
        reminder_level=reminder_level,
        custom_text=custom_template
    ),
    axis=1
)


# ============================================================
# WHATSAPP URL
# ============================================================

def create_whatsapp_url(row):

    phone = row["WhatsApp Phone"]

    if not phone:
        return None

    return (
        f"https://web.whatsapp.com/send?"
        f"phone={phone}"
        f"&text={quote(row['Reminder Message'])}"
    )


data["WhatsApp Link"] = data.apply(
    create_whatsapp_url,
    axis=1
)


# ============================================================
# PENDING AND COMPLETED
# ============================================================

pending = data[
    data["Campaign Status"] == "Pending"
].reset_index(drop=True)


completed = data[
    data["Campaign Status"] == "Completed"
].reset_index(drop=True)


# ============================================================
# CAMPAIGN KEY
# ============================================================

campaign_key = (
    f"{uploaded.name}|"
    f"{trainer}|"
    f"{course}|"
    f"{reminder_level}|"
    f"{custom_template}|"
    f"{len(pending)}"
)


# ============================================================
# RESET STATE WHEN SETTINGS CHANGE
# ============================================================

if (
    st.session_state.campaign_state["key"]
    != campaign_key
):

    st.session_state.campaign_state = {
        "key": campaign_key,
        "sent": set(),
        "batch": 0,
        "started": False,
        "started_at": None
    }


state = st.session_state.campaign_state


# ============================================================
# METRICS
# ============================================================

st.divider()

m1, m2, m3, m4 = st.columns(4)

m1.metric(
    "My Total OECs",
    len(data)
)

m2.metric(
    "Pending",
    len(pending)
)

m3.metric(
    "Completed",
    len(completed)
)

completion_percentage = (
    len(completed)
    / len(data)
    * 100
    if len(data)
    else 0
)

m4.metric(
    "Completion %",
    f"{completion_percentage:.1f}%"
)


# ============================================================
# TYPE SUMMARY
# ============================================================

if "TYPE" in data.columns:

    with st.expander(
        "View channel/type summary"
    ):

        summary = (
            data
            .groupby("TYPE")
            .agg(
                Total=(
                    "OEC Name",
                    "size"
                ),
                Pending=(
                    "Campaign Status",
                    lambda x:
                    (x == "Pending").sum()
                ),
                Completed=(
                    "Campaign Status",
                    lambda x:
                    (x == "Completed").sum()
                )
            )
            .reset_index()
        )

        st.dataframe(
            summary,
            use_container_width=True,
            hide_index=True
        )


# ============================================================
# NO PENDING
# ============================================================

st.divider()

st.subheader(
    "WhatsApp Reminder Campaign"
)


if len(pending) == 0:

    st.success(
        "No pending OECs for this course "
        "in the latest report."
    )

    st.stop()


# ============================================================
# BATCH CALCULATIONS
# ============================================================

total_batches = (
    len(pending)
    + BATCH_SIZE
    - 1
) // BATCH_SIZE


state["batch"] = min(
    state["batch"],
    total_batches - 1
)


batch_start = (
    state["batch"]
    * BATCH_SIZE
)


batch_end = min(
    batch_start + BATCH_SIZE,
    len(pending)
)


current_batch = pending.iloc[
    batch_start:batch_end
].copy()


# ============================================================
# CAMPAIGN HEADER
# ============================================================

h1, h2, h3 = st.columns(
    [1, 1, 2]
)


with h1:

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

        st.success(
            "Campaign Active"
        )


with h2:

    st.metric(
        "Marked Sent",
        len(state["sent"])
    )


with h3:

    if state["started_at"]:

        st.caption(
            f"Started: "
            f"{state['started_at']}"
        )


# ============================================================
# PROGRESS
# ============================================================

progress = min(
    len(state["sent"])
    / len(pending),
    1.0
)


st.progress(progress)

st.caption(
    f"Batch {state['batch'] + 1} "
    f"of {total_batches} • "
    f"OECs {batch_start + 1}-{batch_end} "
    f"of {len(pending)} pending OECs"
)


# ============================================================
# BATCH NAVIGATION
# ============================================================

nav1, nav2, nav3 = st.columns(
    [1, 2, 1]
)


with nav1:

    if st.button(
        "Previous Batch",
        disabled=(
            state["batch"] == 0
        ),
        use_container_width=True
    ):

        state["batch"] -= 1

        st.rerun()


with nav2:

    st.markdown(
        f"""
        <div style="
        text-align:center;
        padding:8px;
        font-size:16px;">
        Showing <b>{len(current_batch)}</b>
        OECs in this batch
        </div>
        """,
        unsafe_allow_html=True
    )


with nav3:

    if st.button(
        "Next Batch",
        disabled=(
            state["batch"]
            >= total_batches - 1
        ),
        use_container_width=True
    ):

        state["batch"] += 1

        st.rerun()


st.divider()


# ============================================================
# CURRENT BATCH
# ============================================================

st.subheader(
    f"Current Batch – {len(current_batch)} OECs"
)


if not state["started"]:

    st.info(
        "Click Start Campaign before opening "
        "WhatsApp message drafts."
    )


# ============================================================
# OEC CARDS
# ============================================================

for batch_position, (
    original_index,
    row
) in enumerate(
    current_batch.iterrows(),
    start=batch_start + 1
):

    # Unique identity for sent status
    oec_key = (
        row["Employee ID"]
        if row["Employee ID"]
        else f"{row['OEC Name']}_{original_index}"
    )

    is_sent = (
        oec_key
        in state["sent"]
    )

    status_text = (
        "Sent"
        if is_sent
        else "Pending"
    )


    with st.container(
        border=True
    ):

        top1, top2, top3, top4 = st.columns(
            [2, 2, 2, 2]
        )

        with top1:

            st.markdown(
                f"### {batch_position}. "
                f"{row['OEC Name']}"
            )

            st.caption(
                f"Employee ID: "
                f"{row['Employee ID']}"
            )


        with top2:

            st.write(
                f"**Store:** "
                f"{row.get('Store', '')}"
            )


        with top3:

            st.write(
                f"**Course Status:** "
                f"{row['Course Status']}"
            )

            st.write(
                f"**Type:** "
                f"{row.get('TYPE', '')}"
            )


        with top4:

            if row["WhatsApp Phone"]:

                st.success(
                    "Number Updated"
                )

                st.caption(
                    row["WhatsApp Phone"]
                )

            else:

                st.error(
                    "Number not updated "
                    "in the system"
                )


        # Personalized message preview
        with st.expander(
            "View personalized message",
            expanded=False
        ):

            st.text_area(
                "Message Preview",
                value=row[
                    "Reminder Message"
                ],
                height=130,
                disabled=True,
                key=(
                    f"preview_"
                    f"{campaign_key}_"
                    f"{original_index}"
                )
            )


        # Buttons
        b1, b2 = st.columns(2)


        with b1:

            open_draft = st.button(
                "Open WhatsApp Draft",
                disabled=(
                    not state["started"]
                    or not row["WhatsApp Phone"]
                ),
                use_container_width=True,
                key=(
                    f"open_"
                    f"{campaign_key}_"
                    f"{original_index}"
                )
            )

            if open_draft:

                open_whatsapp_same_tab(
                    row["WhatsApp Phone"],
                    row["Reminder Message"]
                )

                st.success(
                    "Draft opened in the same "
                    "WhatsApp Web tab."
                )


        with b2:

            button_text = (
                "Sent"
                if is_sent
                else "Mark as Sent"
            )

            if st.button(
                button_text,
                disabled=(
                    not state["started"]
                    or is_sent
                    or not row["WhatsApp Phone"]
                ),
                use_container_width=True,
                key=(
                    f"sent_"
                    f"{campaign_key}_"
                    f"{original_index}"
                )
            ):

                state["sent"].add(
                    oec_key
                )

                st.rerun()


        st.caption(
            f"Session Status: {status_text}"
        )


# ============================================================
# BATCH STATUS
# ============================================================

st.divider()

st.subheader(
    "Batch Progress"
)


batch_sent = 0

for original_index, row in current_batch.iterrows():

    oec_key = (
        row["Employee ID"]
        if row["Employee ID"]
        else f"{row['OEC Name']}_{original_index}"
    )

    if oec_key in state["sent"]:

        batch_sent += 1


st.write(
    f"Marked sent in this batch: "
    f"**{batch_sent} / {len(current_batch)}**"
)


if batch_sent == len(current_batch):

    st.success(
        "This batch has been completed. "
        "You can move to the next batch."
    )


# ============================================================
# REMAINING OEC TABLE
# ============================================================

st.divider()

st.subheader(
    "My Pending OEC Queue"
)


queue = pending.copy()


def get_session_status(row):

    key = (
        row["Employee ID"]
        if row["Employee ID"]
        else f"{row['OEC Name']}_{row.name}"
    )

    return (
        "Marked Sent"
        if key in state["sent"]
        else "Pending Send"
    )


queue["Session Status"] = queue.apply(
    get_session_status,
    axis=1
)


display_columns = [
    "OEC Name",
    "Employee ID",
    "Mob No",
    "Phone Status",
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
    queue[
        available_columns
    ],
    use_container_width=True,
    height=400,
    hide_index=True
)


# ============================================================
# DOWNLOAD QUEUE
# ============================================================

download_columns = [
    "OEC Name",
    "Employee ID",
    "Mob No",
    "Phone Status",
    "Store",
    "TYPE",
    "Course Status",
    "Session Status",
    "Reminder Message"
]


available_download_columns = [
    column
    for column in download_columns
    if column in queue.columns
]


csv_data = (
    queue[
        available_download_columns
    ]
    .to_csv(index=False)
    .encode("utf-8-sig")
)


safe_trainer = (
    trainer
    .replace(" ", "_")
    .replace("/", "_")
)


safe_course = (
    course
    .replace(" ", "_")
    .replace("/", "_")
)


st.download_button(
    "Download My Campaign Queue (CSV)",
    csv_data,
    file_name=(
        f"OYE_"
        f"{safe_trainer}_"
        f"{safe_course}.csv"
    ),
    mime="text/csv"
)


# ============================================================
# RESET SESSION
# ============================================================

st.divider()


if st.button(
    "Reset My Campaign Session"
):

    st.session_state.campaign_state = {
        "key": campaign_key,
        "sent": set(),
        "batch": 0,
        "started": False,
        "started_at": None
    }

    st.rerun()


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "WhatsApp reminder workflow: Open personalized draft → "
    "WhatsApp Web opens in the reusable OYE WhatsApp tab → "
    "Manually click Send → Return here → Mark as Sent."
)

st.caption(
    "The message will be sent from whichever WhatsApp account "
    "is currently logged into WhatsApp Web on that trainer's device."
)
