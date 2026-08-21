import streamlit as st
import pandas as pd
import re
from io import BytesIO
from urllib.parse import quote
from datetime import datetime

# ---------------------------------------------------
# PAGE SETTINGS
# ---------------------------------------------------

st.set_page_config(
    page_title="OYE Course Reminder Hub",
    page_icon="📚",
    layout="wide"
)


# ---------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------

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


# ---------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------

def clean_column_name(column):
    """Clean column names from Excel."""
    return str(column).strip()


def clean_phone(value):
    """
    Convert phone number into international format.
    Assumes Indian numbers.
    """

    if pd.isna(value):
        return ""

    phone = re.sub(r"\D", "", str(value))

    # Remove leading 91 if number is 12 digits
    if len(phone) == 12 and phone.startswith("91"):
        return phone

    # Normal Indian mobile number
    if len(phone) == 10:
        return "91" + phone

    return phone


def split_name_emp(value):
    """
    Example:
    Abdullah C T-5005851

    Returns:
    Abdullah C T
    5005851
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
    """
    Detect all course columns.
    """

    fixed_lower = {
        str(column).strip().lower()
        for column in FIXED_COLUMNS
    }

    courses = []

    for column in df.columns:

        column_name = str(column).strip()

        if column_name.lower() not in fixed_lower:
            courses.append(column)

    return courses


def get_course_status(value):

    if pd.isna(value):
        return "Not started"

    value = str(value).strip()

    if value == "":
        return "Not started"

    return value


def status_class(value):
    """
    Decide whether OEC is completed or pending.
    """

    status = str(value).strip().lower()

    completed_keywords = [
        "completed",
        "complete"
    ]

    if status in completed_keywords:
        return "Completed"

    return "Pending"


def build_message(
    name,
    course,
    status,
    reminder_level,
    custom_text=""
):

    name = str(name)
    course = str(course)
    status = str(status)

    # Custom template
    if custom_text and custom_text.strip():

        message = custom_text

        message = message.replace("{name}", name)
        message = message.replace("{course}", course)
        message = message.replace("{status}", status)

        return message

    # Standard templates

    if reminder_level == "First Reminder":

        return (
            f"Hi {name}, your *{course}* course on OYE is currently "
            f"showing as *{status}*. Please complete the course as soon "
            f"as possible. This is mandatory."
        )

    elif reminder_level == "Second Reminder":

        return (
            f"Reminder: Hi {name}, your *{course}* course is still "
            f"showing as *{status}* on OYE. Please complete this "
            f"mandatory course immediately."
        )

    else:

        return (
            f"🚨 *URGENT REMINDER*\n\n"
            f"Hi {name}, your *{course}* course is still pending on OYE.\n\n"
            f"Please complete it immediately."
        )


def get_whatsapp_link(phone, message):

    phone = clean_phone(phone)

    if not phone:
        return ""

    encoded_message = quote(message)

    return (
        f"https://wa.me/{phone}"
        f"?text={encoded_message}"
    )


# ---------------------------------------------------
# LOAD EXCEL
# ---------------------------------------------------

@st.cache_data(show_spinner=False)
def load_report(file_bytes):

    # IMPORTANT:
    # Convert bytes into a file-like object
    # This fixes the:
    # Expected file path name or file-like object, got bytes
    # error.

    excel_file = BytesIO(file_bytes)

    df = pd.read_excel(
        excel_file,
        engine="openpyxl"
    )

    # Clean Excel column names
    df.columns = [
        clean_column_name(column)
        for column in df.columns
    ]

    return df


# ---------------------------------------------------
# HEADER
# ---------------------------------------------------

st.title("OYE Course Reminder Hub")

st.caption(
    "Shared trainer dashboard • Upload OYE report • "
    "Select trainer • Send individual reminders"
)


# ---------------------------------------------------
# SESSION STATE
# ---------------------------------------------------

if "campaign_state" not in st.session_state:

    st.session_state.campaign_state = {
        "key": "",
        "index": 0,
        "sent": set(),
        "started": False,
        "started_at": None
    }


# ---------------------------------------------------
# SIDEBAR
# ---------------------------------------------------

with st.sidebar:

    st.header("Admin / Report")

    uploaded = st.file_uploader(
        "Upload latest OYE Excel",
        type=["xlsx", "xls"]
    )

    st.caption(
        "Upload the newest report whenever OYE "
        "completion status changes."
    )

    st.divider()

    st.header("How trainers use it")

    st.markdown(
        """
        1. Upload latest report
        2. Select your name
        3. Select course
        4. Open WhatsApp chat
        5. Send message
        6. Mark Sent + Next
        """
    )


# ---------------------------------------------------
# WAIT FOR FILE
# ---------------------------------------------------

if uploaded is None:

    st.info(
        "Upload the latest OYE Excel report from "
        "the left panel to start."
    )

    st.stop()


# ---------------------------------------------------
# READ EXCEL
# ---------------------------------------------------

try:

    file_bytes = uploaded.getvalue()

    raw = load_report(file_bytes)

except Exception as error:

    st.error(
        f"Could not read the Excel file: {error}"
    )

    st.info(
        "Please make sure the file is a valid "
        ".xlsx Excel file."
    )

    st.stop()


# ---------------------------------------------------
# CHECK REQUIRED COLUMNS
# ---------------------------------------------------

missing_columns = []

for required_column in REQUIRED_COLUMNS:

    if required_column not in raw.columns:

        missing_columns.append(required_column)


if missing_columns:

    st.error(
        "Missing required columns: "
        + ", ".join(missing_columns)
    )

    st.subheader("Columns found in your Excel")

    st.write(list(raw.columns))

    st.stop()


# ---------------------------------------------------
# DETECT COURSES
# ---------------------------------------------------

courses = course_columns(raw)

if not courses:

    st.error(
        "No OYE course columns were detected."
    )

    st.stop()


# ---------------------------------------------------
# GET TRAINERS
# ---------------------------------------------------

trainers = sorted(
    raw["Trainer Name"]
    .dropna()
    .astype(str)
    .str.strip()
    .unique()
)


if not trainers:

    st.error(
        "No Trainer Name was found in the report."
    )

    st.stop()


# ---------------------------------------------------
# SETTINGS
# ---------------------------------------------------

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
        "Example:\n"
        "Hi {name}, your {course} course is {status}. "
        "Please complete it today."
    ),
    height=120
)


# ---------------------------------------------------
# FILTER SELECTED TRAINER
# ---------------------------------------------------

data = raw[
    raw["Trainer Name"]
    .astype(str)
    .str.strip()
    .eq(str(trainer).strip())
].copy()


# ---------------------------------------------------
# CREATE OEC NAME AND EMPLOYEE ID
# ---------------------------------------------------

data[
    ["OEC Name", "Employee ID"]
] = data[
    "employee's name"
].apply(
    lambda value: pd.Series(
        split_name_emp(value)
    )
)


# ---------------------------------------------------
# CLEAN WHATSAPP NUMBER
# ---------------------------------------------------

data["WhatsApp Phone"] = data[
    "Mob No"
].apply(clean_phone)


# ---------------------------------------------------
# COURSE STATUS
# ---------------------------------------------------

data["Course Status"] = data[
    course
].apply(get_course_status)


# ---------------------------------------------------
# CAMPAIGN STATUS
# ---------------------------------------------------

data["Campaign Status"] = data[
    "Course Status"
].apply(status_class)


# ---------------------------------------------------
# BUILD REMINDER MESSAGE
# ---------------------------------------------------

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


# ---------------------------------------------------
# CREATE WHATSAPP LINK
# ---------------------------------------------------

data["WhatsApp Link"] = data.apply(

    lambda row: get_whatsapp_link(

        row["WhatsApp Phone"],

        row["Reminder Message"]

    ),

    axis=1

)


# ---------------------------------------------------
# PENDING AND COMPLETED
# ---------------------------------------------------

pending = data[
    data["Campaign Status"] == "Pending"
].reset_index(drop=True)


completed = data[
    data["Campaign Status"] == "Completed"
].reset_index(drop=True)


# ---------------------------------------------------
# CAMPAIGN KEY
# ---------------------------------------------------

campaign_key = (
    f"{uploaded.name}|"
    f"{trainer}|"
    f"{course}|"
    f"{reminder_level}"
)


# ---------------------------------------------------
# RESET SESSION WHEN TRAINER / COURSE CHANGES
# ---------------------------------------------------

if (
    st.session_state.campaign_state["key"]
    != campaign_key
):

    st.session_state.campaign_state = {

        "key": campaign_key,

        "index": 0,

        "sent": set(),

        "started": False,

        "started_at": None

    }


state = st.session_state.campaign_state


# ---------------------------------------------------
# METRICS
# ---------------------------------------------------

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


completion_percentage = 0

if len(data) > 0:

    completion_percentage = (
        len(completed)
        / len(data)
        * 100
    )


metric4.metric(
    "Completion %",
    f"{completion_percentage:.1f}%"
)


# ---------------------------------------------------
# TYPE SUMMARY
# ---------------------------------------------------

if "TYPE" in data.columns:

    with st.expander(
        "View channel/type summary"
    ):

        summary = (
            data
            .groupby("TYPE", dropna=False)
            .agg(
                Total=(
                    "OEC Name",
                    "size"
                ),

                Pending=(
                    "Campaign Status",
                    lambda status:
                    (
                        status == "Pending"
                    ).sum()
                ),

                Completed=(
                    "Campaign Status",
                    lambda status:
                    (
                        status == "Completed"
                    ).sum()
                )
            )
            .reset_index()
        )

        st.dataframe(
            summary,
            use_container_width=True,
            hide_index=True
        )


# ---------------------------------------------------
# CAMPAIGN SECTION
# ---------------------------------------------------

st.divider()

st.subheader(
    "My WhatsApp Reminder Campaign"
)


if len(pending) == 0:

    st.success(
        "No pending OECs for this course "
        "in the latest report."
    )


else:

    top1, top2, top3 = st.columns(
        [1, 1, 2]
    )


    # -----------------------------------------------
    # START CAMPAIGN
    # -----------------------------------------------

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
                    .strftime(
                        "%d-%m-%Y %I:%M %p"
                    )
                )

                st.rerun()

        else:

            st.success(
                "Campaign Active"
            )


    # -----------------------------------------------
    # SENT COUNT
    # -----------------------------------------------

    with top2:

        st.metric(
            "Marked Sent",
            len(state["sent"])
        )


    # -----------------------------------------------
    # START TIME
    # -----------------------------------------------

    with top3:

        if state["started_at"]:

            st.caption(
                f"Started: "
                f"{state['started_at']}"
            )


    # -----------------------------------------------
    # GET CURRENT PERSON
    # -----------------------------------------------

    if state["index"] >= len(pending):

        state["index"] = len(pending) - 1


    idx = state["index"]

    person = pending.iloc[idx]


    # -----------------------------------------------
    # PROGRESS BAR
    # -----------------------------------------------

    progress = (
        (idx + 1)
        / len(pending)
    )

    st.progress(progress)

    st.caption(
        f"Reminder {idx + 1} of "
        f"{len(pending)} pending OECs"
    )


    # -----------------------------------------------
    # PERSON DETAILS
    # -----------------------------------------------

    st.markdown(
        f"### {idx + 1}. "
        f"{person['OEC Name']}"
    )


    detail1, detail2, detail3, detail4 = (
        st.columns(4)
    )


    with detail1:

        st.write(
            f"**Phone:** "
            f"{person['WhatsApp Phone']}"
        )


    with detail2:

        st.write(
            f"**Store:** "
            f"{person.get('Store', '')}"
        )


    with detail3:

        st.write(
            f"**Type:** "
            f"{person.get('TYPE', '')}"
        )


    with detail4:

        st.write(
            f"**OYE Status:** "
            f"{person['Course Status']}"
        )


    # -----------------------------------------------
    # MESSAGE EDITOR
    # -----------------------------------------------

    message = st.text_area(

        "Message",

        value=person["Reminder Message"],

        height=150,

        key=(
            f"message_"
            f"{campaign_key}_"
            f"{idx}"
        )

    )


    # -----------------------------------------------
    # LIVE WHATSAPP LINK
    # -----------------------------------------------

    live_link = get_whatsapp_link(

        person["WhatsApp Phone"],

        message

    )


    # -----------------------------------------------
    # OPEN WHATSAPP
    # -----------------------------------------------

    if state["started"]:

        if live_link:

            st.link_button(

                "Open WhatsApp Chat",

                live_link,

                type="primary",

                use_container_width=True

            )

            st.caption(
                "The link will open the WhatsApp "
                "account currently available on the "
                "trainer's device or browser. It can "
                "work with normal WhatsApp or "
                "WhatsApp Business."
            )

        else:

            st.error(
                "This OEC does not have a valid "
                "WhatsApp phone number."
            )


    else:

        st.info(
            "Click Start Campaign to begin "
            "sending reminders."
        )


    # -----------------------------------------------
    # NAVIGATION BUTTONS
    # -----------------------------------------------

    button1, button2, button3, button4 = (
        st.columns(4)
    )


    # PREVIOUS
    with button1:

        if st.button(

            "Previous",

            disabled=(idx == 0),

            use_container_width=True

        ):

            state["index"] -= 1

            st.rerun()


    # MARK SENT + NEXT
    with button2:

        if st.button(

            "Mark Sent + Next",

            disabled=not state["started"],

            type="primary",

            use_container_width=True

        ):

            state["sent"].add(idx)

            if idx < len(pending) - 1:

                state["index"] += 1

            st.rerun()


    # SKIP
    with button3:

        if st.button(

            "Skip",

            disabled=(
                idx >= len(pending) - 1
            ),

            use_container_width=True

        ):

            state["index"] += 1

            st.rerun()


    # RESET
    with button4:

        if st.button(

            "Reset My Session",

            use_container_width=True

        ):

            st.session_state.campaign_state = {

                "key": campaign_key,

                "index": 0,

                "sent": set(),

                "started": False,

                "started_at": None

            }

            st.rerun()


# ---------------------------------------------------
# PENDING QUEUE
# ---------------------------------------------------

st.divider()

st.subheader(
    "My Pending Queue"
)


view = pending.copy()


# ---------------------------------------------------
# ADD SESSION STATUS
# ---------------------------------------------------

view["Session Status"] = [

    "Marked Sent"

    if index in state["sent"]

    else "Pending Send"

    for index in range(len(view))

]


# ---------------------------------------------------
# TABLE COLUMNS
# ---------------------------------------------------

columns_to_show = [

    "OEC Name",

    "Employee ID",

    "WhatsApp Phone",

    "Store",

    "TYPE",

    "Course Status",

    "Session Status",

    "Reminder Message"

]


available_columns = [

    column

    for column in columns_to_show

    if column in view.columns

]


st.dataframe(

    view[available_columns],

    use_container_width=True,

    height=400,

    hide_index=True

)


# ---------------------------------------------------
# DOWNLOAD CSV
# ---------------------------------------------------

csv_data = (
    view[available_columns]
    .to_csv(index=False)
    .encode("utf-8-sig")
)


safe_trainer = re.sub(
    r'[\\/*?:"<>|]',
    "_",
    str(trainer)
)


safe_course = re.sub(
    r'[\\/*?:"<>|]',
    "_",
    str(course)
)


st.download_button(

    "Download My Campaign Queue (CSV)",

    data=csv_data,

    file_name=(
        f"OYE_"
        f"{safe_trainer}_"
        f"{safe_course}.csv"
    ),

    mime="text/csv"

)


# ---------------------------------------------------
# FOOTER
# ---------------------------------------------------

st.divider()

st.caption(
    "This version works as a shared trainer dashboard. "
    "Each trainer can upload the latest OYE report, select "
    "their own name, and open individual WhatsApp chats "
    "using either normal WhatsApp or WhatsApp Business."
)
