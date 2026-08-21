import streamlit as st
import pandas as pd
import re
import hashlib
from io import BytesIO
from urllib.parse import quote
from datetime import datetime


# ============================================================
# PAGE SETTINGS
# ============================================================

st.set_page_config(
    page_title="OYE Course Reminder Hub",
    page_icon="📚",
    layout="wide"
)


# ============================================================
# CONFIGURATION
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
# HELPER FUNCTIONS
# ============================================================

def normalize_phone(value):
    """
    Converts mobile numbers into WhatsApp format.

    Valid Indian numbers:
    10 digits -> 91XXXXXXXXXX
    12 digits beginning with 91 -> remains valid

    Invalid/missing numbers return empty string.
    """

    if pd.isna(value):
        return ""

    value = str(value).strip()

    if value.lower() in ["", "nan", "none", "null"]:
        return ""

    # Remove .0 from Excel numeric values
    value = re.sub(r"\.0$", "", value)

    # Remove everything except digits
    digits = re.sub(r"\D", "", value)

    # Indian 10-digit number
    if len(digits) == 10 and digits[0] in "6789":
        return "91" + digits

    # Already has country code
    if len(digits) == 12 and digits.startswith("91"):
        return digits

    return ""


def phone_display(phone):
    """
    Displays the phone number without country code.
    """

    if not phone:
        return "Not Updated"

    if phone.startswith("91") and len(phone) == 12:
        return phone[2:]

    return phone


def split_name_employee(value):
    """
    Separates:
    Vishnu V C-5000581

    Into:
    Vishnu V C
    5000581
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


def get_course_columns(df):
    """
    Finds all course columns by excluding fixed employee columns.
    """

    return [
        column
        for column in df.columns
        if column not in FIXED_COLUMNS
    ]


def is_completed(value):
    """
    Treats only 'Completed' as completed.
    Everything else is pending.
    """

    text = str(value).strip().lower()

    return text == "completed"


def clean_status(value):
    """
    Cleans empty course status.
    """

    if pd.isna(value):
        return "Not started"

    value = str(value).strip()

    if value.lower() in ["", "nan", "none", "null"]:
        return "Not started"

    return value


def build_message(
    name,
    course,
    status,
    reminder_level,
    custom_message=""
):
    """
    Builds personalized WhatsApp message.
    """

    if custom_message and custom_message.strip():

        return (
            custom_message
            .replace("{name}", str(name))
            .replace("{course}", str(course))
            .replace("{status}", str(status))
        )

    if reminder_level == "First Reminder":

        return (
            f"Hi {name}, your *{course}* course on OYE is currently "
            f"showing as *{status}*. Please complete the course as soon "
            f"as possible. This is mandatory."
        )

    if reminder_level == "Second Reminder":

        return (
            f"Hi {name}, this is a reminder regarding your *{course}* "
            f"course on OYE. It is still showing as *{status}*. "
            f"Please complete the mandatory course at the earliest."
        )

    return (
        f"URGENT REMINDER: Hi {name}, your *{course}* course on OYE "
        f"is still showing as *{status}*. Please complete it immediately. "
        f"This course is mandatory."
    )


@st.cache_data(show_spinner=False)
def load_excel(file_bytes):
    """
    Reads Excel safely from uploaded bytes.

    This fixes:
    Expected file path name or file-like object,
    got <class 'bytes'>
    """

    return pd.read_excel(BytesIO(file_bytes))


def create_campaign_key(
    file_bytes,
    trainer,
    course,
    reminder_level
):
    """
    Creates a unique campaign identity.
    """

    file_hash = hashlib.md5(file_bytes).hexdigest()

    return (
        f"{file_hash}|"
        f"{trainer}|"
        f"{course}|"
        f"{reminder_level}"
    )


def initialize_campaign(campaign_key):
    """
    Creates campaign session state.
    """

    if (
        "campaign_state" not in st.session_state
        or st.session_state.campaign_state.get("key") != campaign_key
    ):

        st.session_state.campaign_state = {
            "key": campaign_key,
            "started": False,
            "started_at": None,
            "batch": 0,
            "sent_ids": set()
        }


# ============================================================
# HEADER
# ============================================================

st.title("OYE Course Reminder Hub")

st.caption(
    "Upload OYE report • Select trainer and course • "
    "Send personalized WhatsApp reminders in batches of 10"
)


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
        "Upload the newest OYE report whenever course completion "
        "status changes."
    )

    st.divider()

    st.header("How trainers use it")

    st.markdown(
        "1. Upload latest report\n"
        "2. Select your trainer name\n"
        "3. Select course\n"
        "4. Start campaign\n"
        "5. View 10 OECs at a time\n"
        "6. Open personalized WhatsApp draft\n"
        "7. Manually click Send in WhatsApp Web\n"
        "8. Mark OEC as sent\n"
        "9. Move to the next 10"
    )

    st.divider()

    st.info(
        "The system does not automatically send WhatsApp messages. "
        "Each trainer manually clicks Send from their own logged-in "
        "WhatsApp Web account."
    )


# ============================================================
# NO FILE
# ============================================================

if uploaded_file is None:

    st.info(
        "Upload the latest OYE Excel report from the left panel to begin."
    )

    st.stop()


# ============================================================
# LOAD EXCEL
# ============================================================

file_bytes = uploaded_file.getvalue()

try:

    raw = load_excel(file_bytes)

except Exception as error:

    st.error(
        f"Could not read the Excel file: {error}"
    )

    st.stop()


# ============================================================
# CLEAN COLUMN NAMES
# ============================================================

raw.columns = [
    str(column).strip()
    for column in raw.columns
]


# ============================================================
# VALIDATE REQUIRED COLUMNS
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
# FIND COURSES
# ============================================================

courses = get_course_columns(raw)

if not courses:

    st.error(
        "No OYE course columns were detected."
    )

    st.stop()


# ============================================================
# TRAINERS
# ============================================================

trainer_series = (
    raw["Trainer Name"]
    .dropna()
    .astype(str)
    .str.strip()
)

trainers = sorted(
    trainer_series[
        trainer_series != ""
    ].unique()
)

if not trainers:

    st.error(
        "No trainer names were found in the report."
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


custom_template = st.text_area(
    "Optional custom message template",
    placeholder=(
        "Use {name}, {course}, and {status}. "
        "Leave blank to use the standard message."
    ),
    height=100
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
# EXTRACT NAME AND EMPLOYEE ID
# ============================================================

name_employee = data["employee's name"].apply(
    split_name_employee
)

data["OEC Name"] = name_employee.apply(
    lambda x: x[0]
)

data["Employee ID"] = name_employee.apply(
    lambda x: x[1]
)


# ============================================================
# CLEAN PHONE NUMBERS
# ============================================================

data["WhatsApp Phone"] = data["Mob No"].apply(
    normalize_phone
)

data["Phone Display"] = data["WhatsApp Phone"].apply(
    phone_display
)

data["Number Status"] = data["WhatsApp Phone"].apply(
    lambda phone:
    "Number Updated"
    if phone
    else "Number Not Updated"
)


# ============================================================
# COURSE STATUS
# ============================================================

data["Course Status"] = data[course].apply(
    clean_status
)

data["Campaign Status"] = data["Course Status"].apply(
    lambda value:
    "Completed"
    if is_completed(value)
    else "Pending"
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
        custom_message=custom_template
    ),

    axis=1
)


# ============================================================
# CREATE UNIQUE OEC KEY
# ============================================================

data["OEC Key"] = data.apply(

    lambda row:
    f"{row['Employee ID']}|"
    f"{row['OEC Name']}|"
    f"{row['WhatsApp Phone']}",

    axis=1
)


# ============================================================
# FILTER PENDING AND COMPLETED
# ============================================================

pending = data[
    data["Campaign Status"] == "Pending"
].reset_index(drop=True)


completed = data[
    data["Campaign Status"] == "Completed"
].reset_index(drop=True)


# ============================================================
# CAMPAIGN SESSION
# ============================================================

campaign_key = create_campaign_key(
    file_bytes=file_bytes,
    trainer=trainer,
    course=course,
    reminder_level=reminder_level
)

initialize_campaign(campaign_key)

state = st.session_state.campaign_state


# ============================================================
# METRICS
# ============================================================

st.divider()

metric1, metric2, metric3, metric4 = st.columns(4)

metric1.metric(
    "My Total OECs",
    len(data)
)

metric2.metric(
    "Pending",
    len(pending)
)

metric3.metric(
    "Completed",
    len(completed)
)

completion_percentage = (
    len(completed) / len(data) * 100
    if len(data) > 0
    else 0
)

metric4.metric(
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
            .groupby("TYPE", dropna=False)
            .agg(
                Total=("OEC Name", "size"),
                Pending=(
                    "Campaign Status",
                    lambda status:
                    (status == "Pending").sum()
                ),
                Completed=(
                    "Campaign Status",
                    lambda status:
                    (status == "Completed").sum()
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

st.subheader("WhatsApp Reminder Campaign")

if len(pending) == 0:

    st.success(
        "No pending OECs found for this course in the latest report."
    )

    st.stop()


# ============================================================
# START CAMPAIGN
# ============================================================

if not state["started"]:

    start_col1, start_col2 = st.columns([1, 2])

    with start_col1:

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

    with start_col2:

        st.info(
            f"The campaign will show {BATCH_SIZE} pending OECs "
            "at a time."
        )

    st.stop()


# ============================================================
# CAMPAIGN HEADER
# ============================================================

top1, top2, top3 = st.columns([1, 1, 2])

with top1:

    st.success("Campaign Active")


with top2:

    st.metric(
        "Marked Sent",
        len(state["sent_ids"])
    )


with top3:

    if state["started_at"]:

        st.caption(
            f"Campaign started: {state['started_at']}"
        )


# ============================================================
# BATCH CALCULATION
# ============================================================

total_batches = (
    (len(pending) + BATCH_SIZE - 1)
    // BATCH_SIZE
)

state["batch"] = max(
    0,
    min(
        state["batch"],
        total_batches - 1
    )
)

start_index = state["batch"] * BATCH_SIZE

end_index = min(
    start_index + BATCH_SIZE,
    len(pending)
)

current_batch = pending.iloc[
    start_index:end_index
].copy()


# ============================================================
# BATCH NAVIGATION
# ============================================================

nav1, nav2, nav3 = st.columns([1, 2, 1])

with nav1:

    if st.button(
        "Previous Batch",
        disabled=(state["batch"] == 0),
        use_container_width=True
    ):

        state["batch"] -= 1

        st.rerun()


with nav2:

    st.markdown(
        f"""
        <div style="
            text-align:center;
            padding:10px;
            font-size:18px;
        ">
            <b>
                Batch {state["batch"] + 1}
                of {total_batches}
            </b><br>
            Showing OECs {start_index + 1}
            to {end_index}
            of {len(pending)}
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


# ============================================================
# BATCH STATUS
# ============================================================

batch_sent = sum(

    oec_key in state["sent_ids"]

    for oec_key in current_batch["OEC Key"]

)

batch_progress = (
    batch_sent / len(current_batch)
    if len(current_batch) > 0
    else 0
)

st.progress(batch_progress)

st.caption(
    f"{batch_sent} of {len(current_batch)} OECs "
    "marked as sent in this batch."
)


# ============================================================
# IMPORTANT WHATSAPP WEB NOTE
# ============================================================

st.info(
    "WhatsApp Web workflow: Click 'Open WhatsApp Draft'. "
    "The first click opens one WhatsApp Web tab. "
    "Every following OEC uses the same reusable WhatsApp window. "
    "You manually click Send in WhatsApp."
)


# ============================================================
# CURRENT BATCH
# ============================================================

st.subheader(
    f"Current Batch – {len(current_batch)} OECs"
)


# ============================================================
# SHOW EACH OEC
# ============================================================

for position, (_, row) in enumerate(
    current_batch.iterrows(),
    start=start_index + 1
):

    oec_key = row["OEC Key"]

    already_sent = (
        oec_key
        in state["sent_ids"]
    )

    with st.container(border=True):

        info1, info2, info3, info4 = st.columns(
            [1.2, 1.5, 1.2, 1]
        )


        # ----------------------------------------------------
        # OEC NAME
        # ----------------------------------------------------

        with info1:

            st.markdown(
                f"### {position}. {row['OEC Name']}"
            )

            st.caption(
                f"Employee ID: {row['Employee ID']}"
            )


        # ----------------------------------------------------
        # STORE
        # ----------------------------------------------------

        with info2:

            st.markdown(
                f"**Store:** {row.get('Store', '')}"
            )

            st.markdown(
                f"**Type:** {row.get('TYPE', '')}"
            )


        # ----------------------------------------------------
        # COURSE STATUS
        # ----------------------------------------------------

        with info3:

            st.markdown(
                f"**Course Status:** "
                f"{row['Course Status']}"
            )


        # ----------------------------------------------------
        # NUMBER STATUS
        # ----------------------------------------------------

        with info4:

            if row["WhatsApp Phone"]:

                st.success("Number Updated")

                st.caption(
                    row["Phone Display"]
                )

            else:

                st.error(
                    "Number Not Updated"
                )

                st.caption(
                    "Update the number in the OYE system."
                )


        # ----------------------------------------------------
        # PERSONALIZED MESSAGE
        # ----------------------------------------------------

        with st.expander(
            "View personalized message"
        ):

            st.text_area(
                "Message",
                value=row["Reminder Message"],
                height=120,
                disabled=True,
                key=f"message_{campaign_key}_{oec_key}"
            )


        # ----------------------------------------------------
        # WHATSAPP URL
        # ----------------------------------------------------

        if row["WhatsApp Phone"]:

            whatsapp_url = (
                "https://web.whatsapp.com/send"
                f"?phone={row['WhatsApp Phone']}"
                f"&text={quote(row['Reminder Message'])}"
            )


            # ------------------------------------------------
            # SAME REUSABLE WHATSAPP WEB TAB
            # ------------------------------------------------

            st.markdown(
                f"""
                <a
                    href="{whatsapp_url}"
                    target="oye_whatsapp_window"
                    style="
                        display: block;
                        width: 100%;
                        padding: 12px;
                        text-align: center;
                        border-radius: 8px;
                        text-decoration: none;
                        font-weight: bold;
                        color: white;
                        background-color: #25D366;
                        box-sizing: border-box;
                        margin-top: 10px;
                        margin-bottom: 10px;
                    "
                >
                    Open WhatsApp Draft
                </a>
                """,
                unsafe_allow_html=True
            )


            st.caption(
                "Uses the same WhatsApp Web window for every OEC. "
                "It does not automatically send the message."
            )


        else:

            st.warning(
                "WhatsApp draft cannot be opened because "
                "the mobile number is not updated in the system."
            )


        # ----------------------------------------------------
        # MARK SENT BUTTON
        # ----------------------------------------------------

        sent_col1, sent_col2 = st.columns([1, 1])

        with sent_col1:

            if already_sent:

                st.success("Marked as Sent")

            else:

                if st.button(
                    "Mark as Sent",
                    key=f"sent_{campaign_key}_{oec_key}",
                    use_container_width=True
                ):

                    state["sent_ids"].add(
                        oec_key
                    )

                    st.rerun()


        with sent_col2:

            if already_sent:

                if st.button(
                    "Undo Sent Status",
                    key=f"undo_{campaign_key}_{oec_key}",
                    use_container_width=True
                ):

                    state["sent_ids"].discard(
                        oec_key
                    )

                    st.rerun()

            else:

                st.warning(
                    "Not marked as sent"
                )


# ============================================================
# BATCH FOOTER
# ============================================================

st.divider()

footer1, footer2, footer3 = st.columns(
    [1, 1, 1]
)


with footer1:

    if st.button(
        "Previous Batch",
        disabled=(state["batch"] == 0),
        key="bottom_previous_batch",
        use_container_width=True
    ):

        state["batch"] -= 1

        st.rerun()


with footer2:

    if state["batch"] < total_batches - 1:

        if st.button(
            "Next 10 OECs",
            type="primary",
            key="bottom_next_batch",
            use_container_width=True
        ):

            state["batch"] += 1

            st.rerun()

    else:

        st.success(
            "Final batch"
        )


with footer3:

    if st.button(
        "Reset Campaign",
        key="reset_campaign",
        use_container_width=True
    ):

        st.session_state.campaign_state = {
            "key": campaign_key,
            "started": False,
            "started_at": None,
            "batch": 0,
            "sent_ids": set()
        }

        st.rerun()


# ============================================================
# ALL PENDING QUEUE
# ============================================================

st.divider()

st.subheader("All Pending OECs")


queue = pending.copy()


queue["Session Status"] = queue["OEC Key"].apply(

    lambda key:
    "Marked Sent"
    if key in state["sent_ids"]
    else "Pending Send"
)


queue_columns = [

    "OEC Name",
    "Employee ID",
    "Phone Display",
    "Number Status",
    "Store",
    "TYPE",
    "Course Status",
    "Session Status",
    "Reminder Message"
]


available_columns = [

    column
    for column in queue_columns
    if column in queue.columns
]


st.dataframe(
    queue[available_columns],
    use_container_width=True,
    height=400
)


# ============================================================
# DOWNLOAD CSV
# ============================================================

csv_data = (
    queue[available_columns]
    .to_csv(index=False)
    .encode("utf-8-sig")
)


st.download_button(
    "Download Campaign Queue (CSV)",
    data=csv_data,
    file_name=(
        f"OYE_"
        f"{trainer.replace(' ', '_')}_"
        f"{course.replace(' ', '_')}.csv"
    ),
    mime="text/csv"
)


# ============================================================
# FINAL NOTE
# ============================================================

st.divider()

st.caption(
    "Important: The trainer's logged-in WhatsApp Web account is used automatically. "
    "The OYE system does not use a fixed company number inside the code. "
    "Each trainer can use their own company WhatsApp account."
)
