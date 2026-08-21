import streamlit as st
import pandas as pd
import re
from urllib.parse import quote
from datetime import datetime
from io import BytesIO

# ============================================================
# CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="OYE Course Reminder Hub",
    page_icon="📚",
    layout="wide"
)

# Company number - excluded from reminders as a safety measure
COMPANY_NUMBER = "9072587265"

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

def normalize_column_name(column_name):
    return str(column_name).strip().lower()


def get_column(df, target_name):
    """
    Find a column without being affected by extra spaces
    or upper/lower case differences.
    """
    target = normalize_column_name(target_name)

    for column in df.columns:
        if normalize_column_name(column) == target:
            return column

    return None


def clean_phone(value):
    """
    Convert phone number into Indian WhatsApp format.

    Examples:
    9876543210 -> 919876543210
    919876543210 -> 919876543210

    Missing or invalid number -> ""
    """

    if pd.isna(value):
        return ""

    value_str = str(value).strip()

    if value_str.lower() in ["", "nan", "none", "null"]:
        return ""

    digits = re.sub(r"\D", "", value_str)

    # Excel may convert numbers to something like 9876543210.0
    if len(digits) > 10 and digits.endswith("0") and "." in value_str:
        digits = digits[:-1]

    # Standard Indian mobile number
    if len(digits) == 10:
        return "91" + digits

    # Already contains country code
    if len(digits) == 12 and digits.startswith("91"):
        return digits

    # Sometimes +91 is stored as 13 digits with 0?
    if len(digits) == 11 and digits.startswith("0"):
        return "91" + digits[1:]

    return ""


def is_valid_phone(phone):
    """
    Validate Indian mobile number.
    """

    if not phone:
        return False

    if not phone.startswith("91"):
        return False

    return len(phone) == 12


def is_company_number(phone):
    """
    Prevent accidental reminder to the company number.
    """

    return phone.endswith(COMPANY_NUMBER)


def split_name_emp(value):
    """
    Example:
    Abdullah C T-50005805
    ->
    Abdullah C T
    50005805
    """

    if pd.isna(value):
        return "", ""

    text = str(value).strip()

    match = re.search(r"-(\d{5,})$", text)

    if match:
        employee_name = text[:match.start()].strip()
        employee_id = match.group(1)

        return employee_name, employee_id

    return text, ""


def course_columns(df):
    """
    Detect course columns by excluding known fixed columns.
    """

    fixed_normalized = {
        normalize_column_name(column)
        for column in FIXED_COLUMNS
    }

    detected_courses = []

    for column in df.columns:

        column_normalized = normalize_column_name(column)

        if column_normalized not in fixed_normalized:
            detected_courses.append(column)

    return detected_courses


def normalize_status(value):

    if pd.isna(value):
        return "Not started"

    status = str(value).strip()

    if status == "":
        return "Not started"

    return status


def status_class(value):
    """
    Completed = completed
    Everything else = pending
    """

    value_text = str(value).strip().lower()

    if value_text == "completed":
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
    Create personalized WhatsApp message.
    """

    name = str(name).strip()
    course = str(course).strip()
    status = str(status).strip()

    # Custom template
    if custom_template and custom_template.strip():

        message = custom_template.strip()

        message = message.replace("{name}", name)
        message = message.replace("{course}", course)
        message = message.replace("{status}", status)

        return message

    # First reminder
    if reminder_level == "First Reminder":

        return (
            f"Hi {name},\n\n"
            f"Your *{course}* course on OYE is currently showing as "
            f"*{status}*.\n\n"
            f"Please complete the course as soon as possible. "
            f"This is mandatory."
        )

    # Second reminder
    if reminder_level == "Second Reminder":

        return (
            f"Hi {name},\n\n"
            f"This is a reminder regarding your *{course}* course on OYE.\n\n"
            f"Current status: *{status}*\n\n"
            f"The course is still pending. Please complete the mandatory "
            f"course immediately."
        )

    # Final reminder
    return (
        f"Hi {name},\n\n"
        f"*URGENT REMINDER*\n\n"
        f"Your *{course}* course is still pending on OYE.\n\n"
        f"Current status: *{status}*\n\n"
        f"Please complete the course immediately."
    )


@st.cache_data(show_spinner=False)
def load_report(file_bytes, file_name):

    """
    Read uploaded Excel safely.

    BytesIO fixes the error:
    Expected file path name or file-like object,
    got <class 'bytes'>
    """

    file_object = BytesIO(file_bytes)

    if str(file_name).lower().endswith(".xls"):
        return pd.read_excel(
            file_object,
            engine="xlrd"
        )

    return pd.read_excel(
        file_object,
        engine="openpyxl"
    )


# ============================================================
# SESSION STATE
# ============================================================

if "campaign_state" not in st.session_state:

    st.session_state.campaign_state = {
        "key": None,
        "batch": 0,
        "started": False,
        "started_at": None,
        "sent_ids": set(),
        "skipped_ids": set()
    }


# ============================================================
# HEADER
# ============================================================

st.title("OYE Course Reminder Hub")

st.caption(
    "Shared trainer dashboard • Upload OYE report • "
    "Select trainer • Send personalized WhatsApp reminders in batches of 10"
)


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
        "Upload the newest report whenever OYE completion status changes."
    )

    st.divider()

    st.header("How trainers use it")

    st.markdown(
        """
1. Upload latest report
2. Select your name
3. Select course
4. Start campaign
5. Send personalized reminders to 10 OECs
6. Mark each OEC as sent
7. Move to the next 10
        """
    )


# ============================================================
# NO FILE
# ============================================================

if not uploaded:

    st.info(
        "Upload the latest OYE Excel report from the left panel to start."
    )

    st.stop()


# ============================================================
# LOAD EXCEL
# ============================================================

try:

    file_bytes = uploaded.getvalue()

    if not file_bytes:

        st.error(
            "The uploaded Excel file is empty. Please upload it again."
        )

        st.stop()

    raw = load_report(
        file_bytes,
        uploaded.name
    )

except Exception as error:

    st.error(
        f"Could not read the Excel file: {error}"
    )

    st.info(
        "Please ensure the file is a valid .xlsx or .xls file."
    )

    st.stop()


# ============================================================
# FIND REQUIRED COLUMNS
# ============================================================

employee_column = get_column(
    raw,
    "employee's name"
)

phone_column = get_column(
    raw,
    "Mob No"
)

trainer_column = get_column(
    raw,
    "Trainer Name"
)

missing_columns = []

if employee_column is None:
    missing_columns.append("employee's name")

if phone_column is None:
    missing_columns.append("Mob No")

if trainer_column is None:
    missing_columns.append("Trainer Name")


if missing_columns:

    st.error(
        "Missing required columns: "
        + ", ".join(missing_columns)
    )

    st.write("Columns detected in your Excel file:")

    st.write(list(raw.columns))

    st.stop()


# ============================================================
# DETECT COURSES
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
    raw[trainer_column]
    .dropna()
    .astype(str)
    .str.strip()
    .replace("", pd.NA)
    .dropna()
    .unique()
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
        "Example:\n"
        "Hi {name}, your {course} course is {status}. "
        "Please complete it today."
    ),
    height=110,
    help=(
        "You can use {name}, {course}, and {status}. "
        "Leave empty to use the standard personalized message."
    )
)


# ============================================================
# FILTER TRAINER DATA
# ============================================================

data = raw[
    raw[trainer_column]
    .astype(str)
    .str.strip()
    .eq(trainer)
].copy()


# Create name and employee ID
data[["OEC Name", "Employee ID"]] = data[
    employee_column
].apply(
    lambda value: pd.Series(
        split_name_emp(value)
    )
)


# Clean phone numbers
data["WhatsApp Phone"] = data[
    phone_column
].apply(clean_phone)


# ============================================================
# PHONE STATUS
# ============================================================

def phone_status(phone):

    if not phone or not is_valid_phone(phone):

        return "Number not updated in system"

    if is_company_number(phone):

        return "Company number"

    return "Available"


data["Number Status"] = data[
    "WhatsApp Phone"
].apply(phone_status)


# ============================================================
# COURSE STATUS
# ============================================================

data["Course Status"] = data[
    course
].apply(normalize_status)


data["Campaign Status"] = data[
    "Course Status"
].apply(status_class)


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


# Unique campaign row ID
data["Campaign ID"] = data.index.astype(str)


# ============================================================
# WHATSAPP LINK
# ============================================================

def create_whatsapp_link(row):

    phone = row["WhatsApp Phone"]

    if not is_valid_phone(phone):
        return ""

    if is_company_number(phone):
        return ""

    message = quote(
        row["Reminder Message"]
    )

    return (
        f"https://wa.me/{phone}?text={message}"
    )


data["WhatsApp Link"] = data.apply(
    create_whatsapp_link,
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


# Exclude company number from campaign
company_number_rows = pending[
    pending["Number Status"] == "Company number"
].copy()


pending_campaign = pending[
    pending["Number Status"] != "Company number"
].reset_index(drop=True)


# ============================================================
# CAMPAIGN KEY
# ============================================================

campaign_key = (
    f"{uploaded.name}|"
    f"{len(file_bytes)}|"
    f"{trainer}|"
    f"{course}|"
    f"{reminder_level}|"
    f"{custom_template}"
)


if (
    st.session_state.campaign_state["key"]
    != campaign_key
):

    st.session_state.campaign_state = {
        "key": campaign_key,
        "batch": 0,
        "started": False,
        "started_at": None,
        "sent_ids": set(),
        "skipped_ids": set()
    }


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
    if len(data)
    else 0
)

metric4.metric(
    "Completion %",
    f"{completion_percentage:.1f}%"
)


# ============================================================
# NUMBER STATUS
# ============================================================

invalid_count = len(
    pending_campaign[
        pending_campaign["Number Status"]
        == "Number not updated in system"
    ]
)

available_count = len(
    pending_campaign[
        pending_campaign["Number Status"]
        == "Available"
    ]
)


status1, status2, status3 = st.columns(3)

status1.metric(
    "Available WhatsApp Numbers",
    available_count
)

status2.metric(
    "Number Not Updated",
    invalid_count
)

status3.metric(
    "Company Number Excluded",
    len(company_number_rows)
)


# ============================================================
# TYPE SUMMARY
# ============================================================

type_column = get_column(
    data,
    "TYPE"
)

if type_column:

    with st.expander(
        "View channel/type summary"
    ):

        summary = (
            data
            .groupby(type_column)
            .agg(
                Total=("OEC Name", "size"),
                Pending=(
                    "Campaign Status",
                    lambda status: (
                        status == "Pending"
                    ).sum()
                ),
                Completed=(
                    "Campaign Status",
                    lambda status: (
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


# ============================================================
# CAMPAIGN
# ============================================================

st.divider()

st.subheader(
    "My WhatsApp Reminder Campaign"
)


if len(pending_campaign) == 0:

    st.success(
        "No pending OECs are available for this course."
    )

else:

    BATCH_SIZE = 10

    total_batches = (
        len(pending_campaign)
        + BATCH_SIZE
        - 1
    ) // BATCH_SIZE


    # ----------------------------------------
    # START CAMPAIGN
    # ----------------------------------------

    if not state["started"]:

        start_col1, start_col2 = st.columns(
            [1, 3]
        )

        with start_col1:

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


        with start_col2:

            st.info(
                f"This campaign contains "
                f"{len(pending_campaign)} pending OECs "
                f"in {total_batches} batches of maximum 10."
            )


    # ----------------------------------------
    # ACTIVE CAMPAIGN
    # ----------------------------------------

    else:

        current_batch = state["batch"]

        start_index = (
            current_batch * BATCH_SIZE
        )

        end_index = min(
            start_index + BATCH_SIZE,
            len(pending_campaign)
        )

        batch_data = pending_campaign.iloc[
            start_index:end_index
        ].copy()


        # ----------------------------------------
        # CAMPAIGN HEADER
        # ----------------------------------------

        head1, head2, head3, head4 = st.columns(4)

        head1.success(
            f"Batch {current_batch + 1} Active"
        )

        sent_count = len(
            state["sent_ids"]
        )

        head2.metric(
            "Marked Sent",
            sent_count
        )

        head3.metric(
            "This Batch",
            f"{len(batch_data)} OECs"
        )

        if state["started_at"]:

            head4.caption(
                f"Started:\n\n"
                f"{state['started_at']}"
            )


        # Progress bar
        progress = (
            len(state["sent_ids"])
            + len(state["skipped_ids"])
        ) / len(pending_campaign)

        st.progress(
            min(progress, 1.0)
        )

        st.caption(
            f"Batch {current_batch + 1} of "
            f"{total_batches} • "
            f"OECs {start_index + 1} to {end_index} "
            f"of {len(pending_campaign)}"
        )


        # ----------------------------------------
        # BATCH OF 10
        # ----------------------------------------

        for row_position, row in batch_data.iterrows():

            campaign_id = row["Campaign ID"]

            oec_number = (
                start_index
                + row_position
                + 1
            )

            already_sent = (
                campaign_id
                in state["sent_ids"]
            )

            already_skipped = (
                campaign_id
                in state["skipped_ids"]
            )


            # Status heading
            if already_sent:

                st.success(
                    f"Sent: {oec_number}. "
                    f"{row['OEC Name']}"
                )

            elif already_skipped:

                st.warning(
                    f"Skipped: {oec_number}. "
                    f"{row['OEC Name']}"
                )

            else:

                st.markdown(
                    f"### {oec_number}. "
                    f"{row['OEC Name']}"
                )


            # Basic information
            info1, info2, info3, info4 = st.columns(4)

            with info1:

                if (
                    row["Number Status"]
                    == "Available"
                ):

                    st.write(
                        f"**Phone:** "
                        f"{row['WhatsApp Phone']}"
                    )

                else:

                    st.error(
                        "Number not updated in system"
                    )


            with info2:

                store_column = get_column(
                    data,
                    "Store"
                )

                store = (
                    row.get(
                        store_column,
                        ""
                    )
                    if store_column
                    else ""
                )

                st.write(
                    f"**Store:** {store}"
                )


            with info3:

                if type_column:

                    st.write(
                        f"**Type:** "
                        f"{row.get(type_column, '')}"
                    )

                else:

                    st.write(
                        "**Type:** -"
                    )


            with info4:

                st.write(
                    f"**OYE Status:** "
                    f"{row['Course Status']}"
                )


            # Personalized message
            st.text_area(
                "Personalized Message",
                value=row[
                    "Reminder Message"
                ],
                height=120,
                key=(
                    f"message_"
                    f"{campaign_key}_"
                    f"{campaign_id}"
                ),
                disabled=(
                    already_sent
                    or already_skipped
                )
            )


            # Action buttons
            button1, button2, button3 = st.columns(
                [2, 1, 1]
            )


            with button1:

                if (
                    row["Number Status"]
                    == "Available"
                    and not already_sent
                    and not already_skipped
                ):

                    st.link_button(
                        f"Open WhatsApp for "
                        f"{row['OEC Name']}",
                        row["WhatsApp Link"],
                        type="primary",
                        use_container_width=True
                    )

                elif (
                    row["Number Status"]
                    == "Number not updated in system"
                ):

                    st.warning(
                        "Cannot send until "
                        "the mobile number is updated."
                    )


            with button2:

                if st.button(
                    "Mark Sent",
                    key=(
                        f"sent_"
                        f"{campaign_key}_"
                        f"{campaign_id}"
                    ),
                    disabled=(
                        already_sent
                        or already_skipped
                        or row["Number Status"]
                        != "Available"
                    ),
                    use_container_width=True
                ):

                    state[
                        "sent_ids"
                    ].add(
                        campaign_id
                    )

                    st.rerun()


            with button3:

                if st.button(
                    "Skip",
                    key=(
                        f"skip_"
                        f"{campaign_key}_"
                        f"{campaign_id}"
                    ),
                    disabled=(
                        already_sent
                        or already_skipped
                    ),
                    use_container_width=True
                ):

                    state[
                        "skipped_ids"
                    ].add(
                        campaign_id
                    )

                    st.rerun()


            st.divider()


        # ====================================================
        # NEXT BATCH
        # ====================================================

        st.subheader(
            "Batch Controls"
        )

        control1, control2, control3 = st.columns(
            3
        )


        with control1:

            if st.button(
                "Previous Batch",
                disabled=(
                    current_batch == 0
                ),
                use_container_width=True
            ):

                state["batch"] -= 1

                st.rerun()


        with control2:

            if current_batch < total_batches - 1:

                if st.button(
                    "Complete This Batch & Next 10",
                    type="primary",
                    use_container_width=True
                ):

                    state["batch"] += 1

                    st.rerun()

            else:

                if st.button(
                    "Finish Campaign",
                    type="primary",
                    use_container_width=True
                ):

                    st.success(
                        "Campaign completed."
                    )


        with control3:

            if st.button(
                "Reset Campaign",
                use_container_width=True
            ):

                st.session_state.campaign_state = {
                    "key": campaign_key,
                    "batch": 0,
                    "started": False,
                    "started_at": None,
                    "sent_ids": set(),
                    "skipped_ids": set()
                }

                st.rerun()


# ============================================================
# NUMBER NOT UPDATED LIST
# ============================================================

invalid_numbers = pending_campaign[
    pending_campaign["Number Status"]
    == "Number not updated in system"
].copy()


if len(invalid_numbers) > 0:

    st.divider()

    st.subheader(
        "OECs With Number Not Updated"
    )

    invalid_columns = [
        "OEC Name",
        "Employee ID",
        "Store",
        "Course Status",
        "Number Status"
    ]

    invalid_columns = [
        column
        for column in invalid_columns
        if column in invalid_numbers.columns
    ]

    st.dataframe(
        invalid_numbers[
            invalid_columns
        ],
        use_container_width=True,
        hide_index=True
    )


# ============================================================
# FULL QUEUE
# ============================================================

st.divider()

st.subheader(
    "My Pending Queue"
)


queue = pending_campaign.copy()


def session_status(row):

    campaign_id = row["Campaign ID"]

    if campaign_id in state["sent_ids"]:
        return "Marked Sent"

    if campaign_id in state["skipped_ids"]:
        return "Skipped"

    if (
        row["Number Status"]
        != "Available"
    ):
        return "Number not updated in system"

    return "Pending Send"


queue["Session Status"] = queue.apply(
    session_status,
    axis=1
)


queue_columns = [
    "OEC Name",
    "Employee ID",
    "WhatsApp Phone",
    "Number Status",
    "Store",
    "Course Status",
    "Session Status",
    "Reminder Message"
]


queue_columns = [
    column
    for column in queue_columns
    if column in queue.columns
]


st.dataframe(
    queue[queue_columns],
    use_container_width=True,
    height=450
)


# ============================================================
# DOWNLOAD CSV
# ============================================================

st.download_button(
    "Download My Campaign Queue (CSV)",
    queue[
        queue_columns
    ]
    .to_csv(
        index=False
    )
    .encode(
        "utf-8-sig"
    ),
    file_name=(
        f"OYE_"
        f"{trainer.replace(' ', '_')}_"
        f"{str(course).replace(' ', '_')}"
        f".csv"
    ),
    mime="text/csv"
)


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "Each WhatsApp message is personalized with the OEC's name. "
    "This app prepares reminders and opens WhatsApp; the trainer "
    "remains responsible for reviewing and sending each message."
)
