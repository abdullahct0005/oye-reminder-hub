import streamlit as st
import pandas as pd
import re
import html
from io import BytesIO
from urllib.parse import quote


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="OYE Reminder Hub",
    page_icon="📚",
    layout="wide"
)


# ============================================================
# CONFIGURATION
# ============================================================

BATCH_SIZE = 10

FIXED_COLUMNS = {
    "employee's name",
    "mob no",
    "store",
    "duties",
    "superior",
    "entry date",
    "zone",
    "location",
    "active status",
    "trainer name",
    "total course pending",
    "total course completed",
    "total course enrolled",
    "type"
}


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def normalize_text(value):
    """Normalize text for column comparison."""

    return str(value).strip().lower()


def find_column(df, possible_names):
    """
    Find a column regardless of upper/lower case or extra spaces.
    """

    normalized_columns = {
        normalize_text(column): column
        for column in df.columns
    }

    for name in possible_names:
        if normalize_text(name) in normalized_columns:
            return normalized_columns[normalize_text(name)]

    return None


def clean_phone(value):
    """
    Convert Indian phone numbers to WhatsApp international format.

    Example:
    9876543210 -> 919876543210
    +91 98765 43210 -> 919876543210

    Returns empty string for invalid/missing numbers.
    """

    if pd.isna(value):
        return ""

    text = str(value).strip()

    if text.lower() in [
        "",
        "nan",
        "none",
        "null"
    ]:
        return ""

    # Remove Excel decimal .0
    if text.endswith(".0"):
        text = text[:-2]

    digits = re.sub(r"\D", "", text)

    # Normal 10-digit Indian number
    if len(digits) == 10:
        return "91" + digits

    # Already has India country code
    if len(digits) == 12 and digits.startswith("91"):
        return digits

    # Starts with 0
    if len(digits) == 11 and digits.startswith("0"):
        return "91" + digits[1:]

    return ""


def is_valid_phone(phone):
    """
    Validate Indian WhatsApp number format.
    """

    if not phone:
        return False

    if len(phone) != 12:
        return False

    if not phone.startswith("91"):
        return False

    # Indian mobile numbers normally start with 6/7/8/9
    return phone[2] in ["6", "7", "8", "9"]


def split_name_employee_id(value):
    """
    Example:
    Abdullah C T-50005805

    Returns:
    Name: Abdullah C T
    Employee ID: 50005805
    """

    if pd.isna(value):
        return "", ""

    text = str(value).strip()

    match = re.search(
        r"-(\d{5,})$",
        text
    )

    if match:
        return (
            text[:match.start()].strip(),
            match.group(1)
        )

    return text, ""


def normalize_status(value):
    """
    Normalize empty course status.
    """

    if pd.isna(value):
        return "Not started"

    text = str(value).strip()

    if text == "":
        return "Not started"

    return text


def is_completed(status):
    """
    Return True if the course is completed.
    """

    return (
        str(status)
        .strip()
        .lower()
        == "completed"
    )


def get_course_columns(df):
    """
    Detect all course columns.
    """

    course_list = []

    for column in df.columns:

        if normalize_text(column) not in FIXED_COLUMNS:
            course_list.append(column)

    return course_list


def build_message(
    name,
    course,
    status,
    reminder_type,
    custom_message=""
):
    """
    Create personalized WhatsApp reminder.
    """

    name = str(name).strip()
    course = str(course).strip()
    status = str(status).strip()

    # Custom message
    if custom_message.strip():

        message = custom_message.strip()

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

    # First reminder
    if reminder_type == "First Reminder":

        return (
            f"Hi {name},\n\n"
            f"Your *{course}* course on OYE is currently "
            f"showing as *{status}*.\n\n"
            f"Please complete the course as soon as possible. "
            f"This is mandatory."
        )

    # Second reminder
    if reminder_type == "Second Reminder":

        return (
            f"Hi {name},\n\n"
            f"This is a reminder regarding your "
            f"*{course}* course on OYE.\n\n"
            f"Current status: *{status}*\n\n"
            f"Please complete the mandatory course immediately."
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
def load_excel(file_bytes, file_name):
    """
    Safely read Excel bytes.
    """

    file_object = BytesIO(file_bytes)

    # xls requires xlrd
    if file_name.lower().endswith(".xls"):
        return pd.read_excel(
            file_object,
            engine="xlrd"
        )

    # xlsx
    return pd.read_excel(
        file_object,
        engine="openpyxl"
    )


def create_whatsapp_link(phone, message):
    """
    Create WhatsApp draft link.
    """

    encoded_message = quote(message)

    return (
        f"https://wa.me/"
        f"{phone}"
        f"?text={encoded_message}"
    )


def prepare_batch_popup_html(batch_df):
    """
    Create JavaScript that tries to open all WhatsApp chats
    in the current batch.

    Browsers may block some popups/tabs.
    """

    links = []

    for _, row in batch_df.iterrows():

        if row["Number Status"] == "Available":

            links.append(
                row["WhatsApp Link"]
            )

    if not links:
        return None

    javascript_lines = []

    for index, link in enumerate(links):

        safe_link = html.escape(
            link,
            quote=True
        )

        javascript_lines.append(
            f"""
            window.open(
                '{safe_link}',
                '_blank'
            );
            """
        )

    javascript_code = "\n".join(
        javascript_lines
    )

    return f"""
    <script>
    {javascript_code}
    </script>
    """


# ============================================================
# SESSION STATE
# ============================================================

if "current_batch" not in st.session_state:
    st.session_state.current_batch = 0

if "campaign_key" not in st.session_state:
    st.session_state.campaign_key = None

if "batch_prepared" not in st.session_state:
    st.session_state.batch_prepared = False


# ============================================================
# HEADER
# ============================================================

st.title("OYE Course Reminder Hub")

st.caption(
    "Upload OYE Report • Select Trainer • Select Course • "
    "Prepare WhatsApp Drafts in Batches of 10"
)


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.header("OYE Report")

    uploaded_file = st.file_uploader(
        "Upload latest OYE Excel",
        type=["xlsx", "xls"]
    )

    st.divider()

    st.subheader("How it works")

    st.markdown(
        """
1. Upload the latest OYE report
2. Select your trainer name
3. Select the course
4. Click **Prepare 10 WhatsApp Drafts**
5. WhatsApp chats open with personalized messages
6. Manually click Send in WhatsApp
7. Return here
8. Click **Next 10 OECs**
        """
    )

    st.divider()

    st.caption(
        "Each trainer uses their own active "
        "Normal WhatsApp or WhatsApp Business account."
    )


# ============================================================
# FILE REQUIRED
# ============================================================

if uploaded_file is None:

    st.info(
        "Upload the latest OYE Excel report to begin."
    )

    st.stop()


# ============================================================
# LOAD EXCEL
# ============================================================

try:

    file_bytes = uploaded_file.getvalue()

    if not file_bytes:

        st.error(
            "The uploaded file is empty. "
            "Please upload the Excel file again."
        )

        st.stop()

    raw = load_excel(
        file_bytes,
        uploaded_file.name
    )

except Exception as error:

    st.error(
        f"Could not read the Excel file: {error}"
    )

    st.stop()


# ============================================================
# FIND REQUIRED COLUMNS
# ============================================================

employee_column = find_column(
    raw,
    [
        "employee's name",
        "employee name"
    ]
)

phone_column = find_column(
    raw,
    [
        "mob no",
        "mobile number",
        "mobile no",
        "phone"
    ]
)

trainer_column = find_column(
    raw,
    [
        "trainer name",
        "trainer"
    ]
)

store_column = find_column(
    raw,
    [
        "store",
        "store name"
    ]
)

type_column = find_column(
    raw,
    [
        "type"
    ]
)


missing_columns = []

if employee_column is None:
    missing_columns.append(
        "employee's name"
    )

if phone_column is None:
    missing_columns.append(
        "Mob No"
    )

if trainer_column is None:
    missing_columns.append(
        "Trainer Name"
    )


if missing_columns:

    st.error(
        "Required columns are missing: "
        + ", ".join(missing_columns)
    )

    st.write(
        "Columns detected in this Excel:"
    )

    st.write(
        list(raw.columns)
    )

    st.stop()


# ============================================================
# DETECT COURSES
# ============================================================

courses = get_course_columns(raw)

if not courses:

    st.error(
        "No course columns were detected."
    )

    st.stop()


# ============================================================
# TRAINER LIST
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
        "No trainer names were found."
    )

    st.stop()


# ============================================================
# SETTINGS
# ============================================================

setting_col1, setting_col2, setting_col3 = st.columns(3)


with setting_col1:

    selected_trainer = st.selectbox(
        "Select Your Trainer Name",
        trainers
    )


with setting_col2:

    selected_course = st.selectbox(
        "Select Course",
        courses
    )


with setting_col3:

    reminder_type = st.selectbox(
        "Reminder Type",
        [
            "First Reminder",
            "Second Reminder",
            "Final / Urgent Reminder"
        ]
    )


custom_message = st.text_area(
    "Optional Custom Message",
    placeholder=(
        "Hi {name}, your {course} course is "
        "{status}. Please complete it today."
    ),
    help=(
        "Available placeholders: "
        "{name}, {course}, {status}"
    ),
    height=100
)


# ============================================================
# FILTER TRAINER
# ============================================================

data = raw[
    raw[trainer_column]
    .astype(str)
    .str.strip()
    .eq(selected_trainer)
].copy()


# ============================================================
# NAME + EMPLOYEE ID
# ============================================================

data[
    ["OEC Name", "Employee ID"]
] = data[
    employee_column
].apply(
    lambda value: pd.Series(
        split_name_employee_id(value)
    )
)


# ============================================================
# PHONE NUMBER
# ============================================================

data["WhatsApp Phone"] = data[
    phone_column
].apply(
    clean_phone
)


def phone_status(phone):

    if is_valid_phone(phone):
        return "Available"

    return "Number not updated in system"


data["Number Status"] = data[
    "WhatsApp Phone"
].apply(
    phone_status
)


# ============================================================
# COURSE STATUS
# ============================================================

data["Course Status"] = data[
    selected_course
].apply(
    normalize_status
)


data["Campaign Status"] = data[
    "Course Status"
].apply(
    lambda value: (
        "Completed"
        if is_completed(value)
        else "Pending"
    )
)


# ============================================================
# PERSONALIZED MESSAGE
# ============================================================

data["Reminder Message"] = data.apply(
    lambda row: build_message(
        name=row["OEC Name"],
        course=selected_course,
        status=row["Course Status"],
        reminder_type=reminder_type,
        custom_message=custom_message
    ),
    axis=1
)


# ============================================================
# WHATSAPP LINK
# ============================================================

data["WhatsApp Link"] = data.apply(
    lambda row: (
        create_whatsapp_link(
            row["WhatsApp Phone"],
            row["Reminder Message"]
        )
        if row["Number Status"] == "Available"
        else ""
    ),
    axis=1
)


# ============================================================
# FILTER PENDING OECs
# ============================================================

pending = data[
    data["Campaign Status"] == "Pending"
].copy()


completed = data[
    data["Campaign Status"] == "Completed"
].copy()


# Reset index so batch numbers are correct
pending = pending.reset_index(
    drop=True
)


# ============================================================
# CAMPAIGN KEY
# ============================================================

new_campaign_key = (
    f"{uploaded_file.name}|"
    f"{len(file_bytes)}|"
    f"{selected_trainer}|"
    f"{selected_course}|"
    f"{reminder_type}|"
    f"{custom_message}"
)


if st.session_state.campaign_key != new_campaign_key:

    st.session_state.campaign_key = (
        new_campaign_key
    )

    st.session_state.current_batch = 0

    st.session_state.batch_prepared = False


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
    len(completed)
    / len(data)
    * 100
    if len(data)
    else 0
)

metric4.metric(
    "Completion %",
    f"{completion_percentage:.1f}%"
)


available_count = len(
    pending[
        pending["Number Status"]
        == "Available"
    ]
)

missing_number_count = len(
    pending[
        pending["Number Status"]
        != "Available"
    ]
)


status_col1, status_col2 = st.columns(2)

status_col1.metric(
    "WhatsApp Drafts Can Be Prepared",
    available_count
)

status_col2.metric(
    "Number Not Updated",
    missing_number_count
)


# ============================================================
# TYPE SUMMARY
# ============================================================

if type_column:

    with st.expander(
        "View Channel / Type Summary"
    ):

        type_summary = (
            data
            .groupby(type_column)
            .agg(
                Total=(
                    "OEC Name",
                    "size"
                ),
                Pending=(
                    "Campaign Status",
                    lambda x: (
                        x == "Pending"
                    ).sum()
                ),
                Completed=(
                    "Campaign Status",
                    lambda x: (
                        x == "Completed"
                    ).sum()
                )
            )
            .reset_index()
        )

        st.dataframe(
            type_summary,
            use_container_width=True,
            hide_index=True
        )


# ============================================================
# NO PENDING OEC
# ============================================================

if len(pending) == 0:

    st.divider()

    st.success(
        "No pending OECs for this trainer and course."
    )

    st.stop()


# ============================================================
# BATCH CALCULATION
# ============================================================

total_batches = (
    len(pending)
    + BATCH_SIZE
    - 1
) // BATCH_SIZE


# Safety
if st.session_state.current_batch >= total_batches:

    st.session_state.current_batch = (
        total_batches - 1
    )


batch_number = (
    st.session_state.current_batch
)

start_index = (
    batch_number * BATCH_SIZE
)

end_index = min(
    start_index + BATCH_SIZE,
    len(pending)
)


batch_data = pending.iloc[
    start_index:end_index
].copy()


# ============================================================
# BATCH HEADER
# ============================================================

st.divider()

st.subheader(
    f"WhatsApp Draft Batch "
    f"{batch_number + 1} of {total_batches}"
)


st.caption(
    f"Showing OECs {start_index + 1}–{end_index} "
    f"of {len(pending)} pending OECs."
)


batch_available = len(
    batch_data[
        batch_data["Number Status"]
        == "Available"
    ]
)


batch_missing = len(
    batch_data[
        batch_data["Number Status"]
        != "Available"
    ]
)


batch_metric1, batch_metric2 = st.columns(2)

batch_metric1.metric(
    "WhatsApp Drafts In This Batch",
    batch_available
)

batch_metric2.metric(
    "Number Not Updated",
    batch_missing
)


# ============================================================
# PREPARE 10 WHATSAPP DRAFTS
# ============================================================

st.divider()

st.markdown(
    "### Prepare WhatsApp Drafts"
)

st.info(
    "Click the button below to open the WhatsApp chats "
    "for all valid OEC numbers in this batch. "
    "Each chat will contain its own personalized draft. "
    "You manually click Send in WhatsApp."
)


prepare_col1, prepare_col2 = st.columns(
    [2, 3]
)


with prepare_col1:

    if st.button(
        f"Prepare {batch_available} WhatsApp Drafts",
        type="primary",
        use_container_width=True
    ):

        st.session_state.batch_prepared = True


with prepare_col2:

    st.caption(
        "Your browser may block multiple popups. "
        "If that happens, use the individual WhatsApp "
        "buttons shown below."
    )


# ============================================================
# POPUP METHOD
# ============================================================

if st.session_state.batch_prepared:

    st.warning(
        "Preparing multiple WhatsApp chats. "
        "If your browser blocks popups, allow popups "
        "for this Streamlit website."
    )

    popup_html = prepare_batch_popup_html(
        batch_data
    )

    if popup_html:

        st.components.v1.html(
            popup_html,
            height=0
        )

    st.success(
        "WhatsApp draft links were prepared for this batch. "
        "Please check your browser tabs."
    )


# ============================================================
# ALL 10 OECs ON SAME PAGE
# ============================================================

st.divider()

st.subheader(
    "All OECs in This Batch"
)


for display_number, (_, row) in enumerate(
    batch_data.iterrows(),
    start=start_index + 1
):

    with st.container():

        name_col, info_col, action_col = st.columns(
            [2, 3, 2]
        )


        # --------------------------------------------
        # OEC NAME
        # --------------------------------------------

        with name_col:

            st.markdown(
                f"### {display_number}. "
                f"{row['OEC Name']}"
            )

            if row["Employee ID"]:

                st.caption(
                    f"Employee ID: "
                    f"{row['Employee ID']}"
                )


        # --------------------------------------------
        # OEC DETAILS
        # --------------------------------------------

        with info_col:

            if row["Number Status"] == "Available":

                st.write(
                    f"**Phone:** "
                    f"{row['WhatsApp Phone']}"
                )

            else:

                st.error(
                    "Number not updated in system"
                )


            if store_column:

                st.write(
                    f"**Store:** "
                    f"{row.get(store_column, '')}"
                )


            if type_column:

                st.write(
                    f"**Type:** "
                    f"{row.get(type_column, '')}"
                )


            st.write(
                f"**Course Status:** "
                f"{row['Course Status']}"
            )


        # --------------------------------------------
        # WHATSAPP ACTION
        # --------------------------------------------

        with action_col:

            if row["Number Status"] == "Available":

                st.link_button(
                    "Open WhatsApp",
                    row["WhatsApp Link"],
                    type="primary",
                    use_container_width=True
                )

                st.caption(
                    "Personalized message ready."
                )

            else:

                st.button(
                    "Number Not Available",
                    disabled=True,
                    key=(
                        f"invalid_"
                        f"{row['OEC Name']}_"
                        f"{display_number}"
                    ),
                    use_container_width=True
                )


        # --------------------------------------------
        # MESSAGE PREVIEW
        # --------------------------------------------

        with st.expander(
            f"View message for "
            f"{row['OEC Name']}"
        ):

            st.text_area(
                "Personalized WhatsApp Message",
                value=row[
                    "Reminder Message"
                ],
                height=150,
                key=(
                    f"preview_"
                    f"{batch_number}_"
                    f"{display_number}"
                )
            )


        st.divider()


# ============================================================
# NEXT BATCH
# ============================================================

st.subheader(
    "Batch Navigation"
)


nav_col1, nav_col2, nav_col3 = st.columns(3)


with nav_col1:

    if st.button(
        "← Previous 10",
        disabled=(
            batch_number == 0
        ),
        use_container_width=True
    ):

        st.session_state.current_batch -= 1

        st.session_state.batch_prepared = False

        st.rerun()


with nav_col2:

    if batch_number < total_batches - 1:

        if st.button(
            "Next 10 OECs →",
            type="primary",
            use_container_width=True
        ):

            st.session_state.current_batch += 1

            st.session_state.batch_prepared = False

            st.rerun()

    else:

        st.success(
            "This is the final batch."
        )


with nav_col3:

    if st.button(
        "Start From First 10",
        use_container_width=True
    ):

        st.session_state.current_batch = 0

        st.session_state.batch_prepared = False

        st.rerun()


# ============================================================
# MISSING NUMBER LIST
# ============================================================

invalid_numbers = pending[
    pending["Number Status"]
    == "Number not updated in system"
].copy()


if len(invalid_numbers) > 0:

    st.divider()

    st.subheader(
        "OECs With Number Not Updated in System"
    )

    missing_columns_to_show = [
        "OEC Name",
        "Employee ID",
        "WhatsApp Phone"
    ]

    if store_column:
        missing_columns_to_show.append(
            store_column
        )

    if type_column:
        missing_columns_to_show.append(
            type_column
        )

    missing_columns_to_show.append(
        "Course Status"
    )

    st.dataframe(
        invalid_numbers[
            missing_columns_to_show
        ],
        use_container_width=True,
        hide_index=True
    )


# ============================================================
# DOWNLOAD FULL PENDING LIST
# ============================================================

st.divider()

st.subheader(
    "Download Pending OEC List"
)


download_columns = [
    "OEC Name",
    "Employee ID",
    "WhatsApp Phone",
    "Number Status"
]

if store_column:
    download_columns.append(
        store_column
    )

if type_column:
    download_columns.append(
        type_column
    )

download_columns.extend(
    [
        "Course Status",
        "Reminder Message",
        "WhatsApp Link"
    ]
)


st.download_button(
    "Download All Pending OECs (CSV)",
    pending[
        download_columns
    ]
    .to_csv(
        index=False
    )
    .encode(
        "utf-8-sig"
    ),
    file_name=(
        f"OYE_Pending_"
        f"{selected_trainer.replace(' ', '_')}_"
        f"{str(selected_course).replace(' ', '_')}"
        f".csv"
    ),
    mime="text/csv"
)


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "OYE Reminder Hub prepares personalized WhatsApp drafts. "
    "The trainer manually reviews and sends each message "
    "using their own active WhatsApp or WhatsApp Business account."
)
