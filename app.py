import streamlit as st
import pandas as pd
import re
from urllib.parse import quote
from io import BytesIO
from datetime import datetime


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="OYE Course Reminder Hub",
    page_icon="📚",
    layout="wide"
)


# ============================================================
# CONFIGURATION
# ============================================================

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

BATCH_SIZE = 10


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def clean_text(value):
    """
    Convert empty / NaN values to empty text.
    """
    if pd.isna(value):
        return ""

    return str(value).strip()


def clean_phone(value):
    """
    Clean and validate phone number.

    Returns:
        (valid_phone_number, True/False)

    Valid Indian numbers:
    - 10 digits
    - Starts with 6, 7, 8 or 9
    """

    if pd.isna(value):
        return "", False

    value = str(value).strip()

    # Remove .0 caused by Excel numeric values
    value = re.sub(r"\.0$", "", value)

    # Remove everything except digits
    digits = re.sub(r"\D", "", value)

    # Remove India country code if present
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]

    # Validate Indian mobile number
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
        name = value[:match.start()].strip()
        employee_id = match.group(1)

        return name, employee_id

    return value, ""


def get_course_columns(df):
    """
    Detect OYE course columns automatically.
    """

    return [
        column
        for column in df.columns
        if column not in FIXED_COLUMNS
    ]


def get_course_status(value):
    """
    Standardize course status.
    """

    value = clean_text(value)

    if value == "":
        return "Not started"

    return value


def get_campaign_status(value):
    """
    Completed = completed
    Everything else = pending
    """

    value = clean_text(value).lower()

    if value == "completed":
        return "Completed"

    return "Pending"


def build_message(
    name,
    course,
    status,
    reminder_level,
    custom_template=""
):
    """
    Build personalized WhatsApp message.
    """

    name = clean_text(name)
    course = clean_text(course)
    status = clean_text(status)

    # Custom message
    if custom_template.strip():

        message = custom_template

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

    # First Reminder
    if reminder_level == "First Reminder":

        return (
            f"Hi {name},\n\n"
            f"Your *{course}* course on OYE is currently showing as "
            f"*{status}*.\n\n"
            f"Please complete the course as soon as possible. "
            f"This is mandatory."
        )

    # Second Reminder
    elif reminder_level == "Second Reminder":

        return (
            f"Hi {name},\n\n"
            f"This is a reminder that your *{course}* course is still "
            f"showing as *{status}* on OYE.\n\n"
            f"Please complete the mandatory course immediately."
        )

    # Final Reminder
    else:

        return (
            f"Hi {name},\n\n"
            f"URGENT REMINDER:\n\n"
            f"Your *{course}* course is still pending on OYE "
            f"(Status: *{status}*).\n\n"
            f"Please complete it immediately. "
            f"This is mandatory."
        )


def make_whatsapp_url(phone, message):
    """
    Create WhatsApp Web URL.
    """

    return (
        "https://web.whatsapp.com/send"
        f"?phone={phone}"
        f"&text={quote(message)}"
    )


def whatsapp_button(url, label):
    """
    Creates a normal HTML button.

    IMPORTANT:
    All OEC buttons use the SAME target name:

        oye_whatsapp_window

    Therefore the same WhatsApp browser tab/window
    is reused instead of opening new tabs.

    The first click may open WhatsApp.
    Every later click navigates the SAME WhatsApp tab.
    """

    html = f"""
    <a href="{url}"
       target="oye_whatsapp_window"
       style="
            display:block;
            width:100%;
            text-align:center;
            padding:12px 15px;
            border-radius:8px;
            text-decoration:none;
            font-weight:600;
            color:white;
            background-color:#25D366;
            border:1px solid #25D366;
            margin-top:8px;
            margin-bottom:8px;
            box-sizing:border-box;
       ">
        {label}
    </a>
    """

    st.markdown(
        html,
        unsafe_allow_html=True
    )


# ============================================================
# LOAD EXCEL
# ============================================================

@st.cache_data(show_spinner=False)
def load_report(file_bytes):
    """
    Read uploaded Excel safely.

    BytesIO is required because pandas expects
    a file-like object.
    """

    return pd.read_excel(
        BytesIO(file_bytes)
    )


# ============================================================
# SESSION STATE
# ============================================================

if "campaign_state" not in st.session_state:

    st.session_state.campaign_state = {
        "campaign_key": None,
        "batch_number": 0,
        "sent_ids": set(),
        "started": False,
        "started_at": None
    }


# ============================================================
# HEADER
# ============================================================

st.title("OYE Course Reminder Hub")

st.caption(
    "Upload OYE report • Select trainer • Select course • "
    "Send personalized WhatsApp reminders in batches"
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
        "Upload the latest report whenever OYE completion "
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
        6. Open personalized WhatsApp draft  
        7. Manually click Send in WhatsApp  
        8. Mark OEC as sent  
        9. Move to the next 10 OECs  
        """
    )


# ============================================================
# NO FILE
# ============================================================

if uploaded_file is None:

    st.info(
        "Upload the latest OYE Excel report "
        "from the left panel to start."
    )

    st.stop()


# ============================================================
# READ FILE
# ============================================================

try:

    raw = load_report(
        uploaded_file.getvalue()
    )

except Exception as error:

    st.error(
        f"Could not read the Excel file: {error}"
    )

    st.stop()


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
# GET COURSES AND TRAINERS
# ============================================================

courses = get_course_columns(raw)

trainers = sorted(
    raw["Trainer Name"]
    .dropna()
    .astype(str)
    .str.strip()
    .unique()
)


if not courses:

    st.error(
        "No OYE course columns were detected."
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
        "Example:\n"
        "Hi {name}, your {course} course is "
        "{status}. Please complete it today."
    ),
    height=110
)

st.caption(
    "You can use: {name}, {course}, and {status}"
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
# CREATE NAME AND EMPLOYEE ID
# ============================================================

name_employee = data[
    "employee's name"
].apply(
    lambda value: pd.Series(
        split_name_emp(value)
    )
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

phone_result = data[
    "Mob No"
].apply(clean_phone)

data["WhatsApp Phone"] = phone_result.apply(
    lambda result: result[0]
)

data["Valid Number"] = phone_result.apply(
    lambda result: result[1]
)


data["Number Status"] = data.apply(
    lambda row:
        "Number Updated"
        if row["Valid Number"]
        else "Number Not Updated in System",
    axis=1
)


# ============================================================
# COURSE STATUS
# ============================================================

data["Course Status"] = data[
    course
].apply(
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
# WHATSAPP LINK
# ============================================================

data["WhatsApp Link"] = data.apply(
    lambda row:

        make_whatsapp_url(
            row["WhatsApp Phone"],
            row["Reminder Message"]
        )

        if row["Valid Number"]

        else "",

    axis=1
)


# ============================================================
# CREATE UNIQUE ID
# ============================================================

data["Unique ID"] = data.apply(
    lambda row:
        f"{row['Employee ID']}|"
        f"{row['OEC Name']}|"
        f"{row['WhatsApp Phone']}",

    axis=1
)


# ============================================================
# PENDING AND COMPLETED
# ============================================================

pending = data[
    data["Campaign Status"] == "Pending"
].copy()


completed = data[
    data["Campaign Status"] == "Completed"
].copy()


pending = pending.reset_index(
    drop=True
)


completed = completed.reset_index(
    drop=True
)


# ============================================================
# CAMPAIGN KEY
# ============================================================

campaign_key = (
    f"{uploaded_file.name}|"
    f"{trainer}|"
    f"{course}|"
    f"{reminder_level}|"
    f"{len(pending)}"
)


# ============================================================
# RESET WHEN TRAINER / COURSE / FILE CHANGES
# ============================================================

state = st.session_state.campaign_state


if state["campaign_key"] != campaign_key:

    st.session_state.campaign_state = {

        "campaign_key": campaign_key,

        "batch_number": 0,

        "sent_ids": set(),

        "started": False,

        "started_at": None
    }


state = st.session_state.campaign_state


# ============================================================
# METRICS
# ============================================================

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

    len(completed)
    / len(data)
    * 100

    if len(data) > 0

    else 0
)


metric4.metric(
    "Completion %",
    f"{completion_percentage:.1f}%"
)


# ============================================================
# CHANNEL SUMMARY
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
                    lambda series:
                    (series == "Pending").sum()
                ),

                Completed=(
                    "Campaign Status",
                    lambda series:
                    (series == "Completed").sum()
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
# DIVIDER
# ============================================================

st.divider()


# ============================================================
# CAMPAIGN SECTION
# ============================================================

st.subheader(
    "WhatsApp Reminder Campaign"
)


if len(pending) == 0:

    st.success(
        "No pending OECs for this course."
    )

    st.stop()


# ============================================================
# START CAMPAIGN
# ============================================================

top1, top2, top3, top4 = st.columns(4)


with top1:

    if not state["started"]:

        if st.button(
            "Start Campaign",
            type="primary",
            use_container_width=True
        ):

            state["started"] = True

            state["started_at"] = datetime.now().strftime(
                "%d-%m-%Y %I:%M %p"
            )

            st.rerun()

    else:

        st.success(
            "Campaign Active"
        )


with top2:

    st.metric(
        "Marked Sent",
        len(state["sent_ids"])
    )


with top3:

    remaining = (
        len(pending)
        - len(state["sent_ids"])
    )

    st.metric(
        "Remaining",
        remaining
    )


with top4:

    if state["started_at"]:

        st.caption(
            "Started: "
            + state["started_at"]
        )


if not state["started"]:

    st.info(
        "Click Start Campaign to begin."
    )


# ============================================================
# BATCH CALCULATION
# ============================================================

total_batches = (

    (len(pending) + BATCH_SIZE - 1)
    // BATCH_SIZE
)


current_batch_number = state[
    "batch_number"
]


start_index = (

    current_batch_number
    * BATCH_SIZE
)


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


nav1, nav2, nav3 = st.columns(
    [1, 2, 1]
)


with nav1:

    if st.button(
        "← Previous Batch",
        disabled=(
            current_batch_number == 0
        ),
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
            font-weight:600;
        ">
            Batch {current_batch_number + 1}
            of {total_batches}
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
    "Use the WhatsApp buttons one at a time. "
    "Every valid OEC opens in the SAME reusable WhatsApp Web tab. "
    "Send manually in WhatsApp, then return here and mark the OEC as sent."
)


# ============================================================
# SHOW EACH OEC
# ============================================================

for position, (_, row) in enumerate(
    batch.iterrows(),
    start=start_index + 1
):

    oec_id = row[
        "Unique ID"
    ]


    # --------------------------------------------------------
    # OEC HEADER
    # --------------------------------------------------------

    with st.container(
        border=True
    ):

        left, middle, right = st.columns(
            [1.3, 2, 1.3]
        )


        # ----------------------------------------------------
        # NAME
        # ----------------------------------------------------

        with left:

            st.markdown(
                f"### {position}. "
                f"{row['OEC Name']}"
            )

            st.caption(
                "Employee ID: "
                + (
                    row["Employee ID"]
                    if row["Employee ID"]
                    else "Not available"
                )
            )


        # ----------------------------------------------------
        # STORE / COURSE
        # ----------------------------------------------------

        with middle:

            st.write(
                f"**Store:** "
                f"{row.get('Store', '')}"
            )

            st.write(
                f"**Course Status:** "
                f"{row['Course Status']}"
            )

            if "TYPE" in row.index:

                st.write(
                    f"**Type:** "
                    f"{row.get('TYPE', '')}"
                )


        # ----------------------------------------------------
        # NUMBER STATUS
        # ----------------------------------------------------

        with right:

            if row["Valid Number"]:

                st.success(
                    "Number Updated"
                )

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
                        "Current value: "
                        + original_number
                    )


        # ----------------------------------------------------
        # MESSAGE
        # ----------------------------------------------------

        with st.expander(
            "View personalized message"
        ):

            st.text_area(

                "Message",

                value=row[
                    "Reminder Message"
                ],

                height=130,

                disabled=True,

                key=(
                    f"message_"
                    f"{campaign_key}_"
                    f"{oec_id}"
                )
            )


        # ----------------------------------------------------
        # INVALID NUMBER
        # ----------------------------------------------------

        if not row["Valid Number"]:

            st.warning(
                "This OEC cannot be opened in WhatsApp because "
                "a valid mobile number is not available."
            )


        # ----------------------------------------------------
        # VALID NUMBER
        # ----------------------------------------------------

        else:

            whatsapp_button(

                row["WhatsApp Link"],

                "Open Personalized WhatsApp Draft"
            )

            st.caption(
                "The first click opens WhatsApp Web. "
                "After that, every OEC button reuses the same "
                "WhatsApp browser tab/window."
            )


        # ----------------------------------------------------
        # MARK AS SENT
        # ----------------------------------------------------

        button1, button2 = st.columns(
            2
        )


        with button1:

            already_sent = (
                oec_id
                in state["sent_ids"]
            )


            if already_sent:

                st.success(
                    "Marked as Sent"
                )

            else:

                if st.button(

                    "Mark as Sent",

                    key=(
                        f"sent_"
                        f"{campaign_key}_"
                        f"{oec_id}"
                    ),

                    use_container_width=True
                ):

                    state[
                        "sent_ids"
                    ].add(
                        oec_id
                    )

                    st.rerun()


        with button2:

            if not row["Valid Number"]:

                st.warning(
                    "Number not available"
                )

            elif oec_id in state[
                "sent_ids"
            ]:

                st.success(
                    "Session Status: Sent"
                )

            else:

                st.info(
                    "Session Status: Pending"
                )


# ============================================================
# BATCH NAVIGATION AGAIN
# ============================================================

st.divider()


bottom1, bottom2, bottom3 = st.columns(
    [1, 2, 1]
)


with bottom1:

    if st.button(
        "← Previous Batch ",
        disabled=(
            current_batch_number == 0
        ),
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
            font-weight:600;
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
# RESET SESSION
# ============================================================

st.divider()


if st.button(
    "Reset My Campaign Session",
    use_container_width=True
):

    st.session_state.campaign_state = {

        "campaign_key": campaign_key,

        "batch_number": 0,

        "sent_ids": set(),

        "started": False,

        "started_at": None
    }

    st.rerun()


# ============================================================
# PENDING QUEUE
# ============================================================

st.divider()


st.subheader(
    "My Pending Queue"
)


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

    queue[
        available_columns
    ],

    use_container_width=True,

    hide_index=True,

    height=400
)


# ============================================================
# DOWNLOAD CAMPAIGN REPORT
# ============================================================

download_data = queue[
    available_columns
].to_csv(
    index=False
).encode(
    "utf-8-sig"
)


st.download_button(

    "Download My Campaign Queue (CSV)",

    data=download_data,

    file_name=(
        f"OYE_"
        f"{trainer.replace(' ', '_')}_"
        f"{course.replace(' ', '_')}.csv"
    ),

    mime="text/csv",

    use_container_width=True
)


# ============================================================
# FOOTER
# ============================================================

st.divider()


st.caption(
    "OYE Reminder Hub • WhatsApp messages are not sent automatically. "
    "The trainer manually sends each personalized draft in WhatsApp Web."
)
