import streamlit as st
import pandas as pd
import re
import math
import hashlib
import html
from io import BytesIO
from urllib.parse import quote
from datetime import datetime

st.set_page_config(
    page_title="OYE & Training Reminder Hub",
    page_icon="📚",
    layout="wide",
)

BATCH_SIZE = 10

FIXED_COLUMNS = {
    "employee's name", "employee name", "name", "oec name", "participant name",
    "mob no", "mobile", "mobile no", "mobile number", "phone", "phone number",
    "trainer name", "trainer", "store", "store name", "duties", "duty",
    "superior", "entry date", "zone", "location", "active status",
    "total course pending", "total course completed", "total course enrolled",
    "type", "group", "category", "channel", "employee id", "emp id", "id"
}

NAME_CANDIDATES = [
    "employee's name", "employee name", "name", "oec name", "participant name"
]
PHONE_CANDIDATES = [
    "mob no", "mobile", "mobile no", "mobile number", "phone", "phone number"
]
TRAINER_CANDIDATES = ["trainer name", "trainer"]
TYPE_CANDIDATES = ["type", "group", "category", "channel"]

st.markdown("""
<style>
.block-container {padding-top: 1.2rem; padding-bottom: 2rem;}
.reminder-card {
    border: 1px solid rgba(151,166,195,.25);
    border-radius: 14px;
    padding: 14px 18px;
    margin-bottom: 10px;
    background: rgba(255,255,255,.02);
}
.queue-box {
    border: 1px solid rgba(37,211,102,.35);
    border-radius: 14px;
    padding: 18px;
    margin: 12px 0 20px;
    background: rgba(37,211,102,.06);
}
.small-muted {color:#9ca3af;font-size:.9rem;}
.wa-open-button {
    display:block;
    width:100%;
    text-align:center;
    padding:13px 18px;
    border-radius:9px;
    text-decoration:none;
    font-weight:700;
    color:white!important;
    background:#25D366;
    border:1px solid #25D366;
    box-sizing:border-box;
    margin:6px 0 12px;
}
</style>
""", unsafe_allow_html=True)


# ============================================================
# HELPERS
# ============================================================

def clean_text(value):
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def norm_column(value):
    return re.sub(r"\s+", " ", clean_text(value).lower()).strip()


def find_column(df, candidates):
    normalized = {norm_column(c): c for c in df.columns}

    for candidate in candidates:
        if candidate in normalized:
            return normalized[candidate]

    for col in df.columns:
        normalized_col = norm_column(col)
        for candidate in candidates:
            if candidate in normalized_col or normalized_col in candidate:
                return col

    return None


def clean_phone(value):
    value = clean_text(value)

    if not value:
        return "", False

    value = re.sub(r"\.0$", "", value)
    digits = re.sub(r"\D", "", value)

    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]

    if len(digits) == 10 and digits[0] in "6789":
        return "91" + digits, True

    return "", False


def split_name_emp(value):
    value = clean_text(value)

    match = re.search(r"\s*-\s*(\d{5,})$", value)

    if match:
        return value[:match.start()].strip(), match.group(1)

    return value, ""


def get_employee_id(row, name_col):
    for col in row.index:
        if norm_column(col) in {"employee id", "emp id", "id"}:
            value = clean_text(row.get(col))
            if value:
                return value

    return split_name_emp(row.get(name_col, ""))[1]


def get_course_columns(df):
    courses = []

    for col in df.columns:
        normalized = norm_column(col)

        if (
            normalized not in FIXED_COLUMNS
            and not normalized.startswith("unnamed")
        ):
            courses.append(col)

    return courses


def get_course_status(value):
    value = clean_text(value)
    return value if value else "Not started"


def is_completed(value):
    return clean_text(value).lower() in {
        "completed",
        "complete",
        "100%",
        "done",
        "finished",
        "finish",
    }


def render_template(template, values):
    message = clean_text(template)

    for key, value in values.items():
        message = message.replace(
            "{" + key + "}",
            clean_text(value),
        )

    return message


def build_oye_message(
    name,
    course,
    status,
    reminder_level,
    custom_template,
):
    if clean_text(custom_template):
        return render_template(
            custom_template,
            {
                "name": name,
                "course": course,
                "status": status,
            },
        )

    if reminder_level == "Second Reminder":
        return (
            f"Hi {name},\n\n"
            f"This is a reminder that your *{course}* course on OYE "
            f"is still showing as *{status}*.\n\n"
            "Please complete the course as soon as possible. "
            "This is mandatory."
        )

    if reminder_level == "Final / Urgent Reminder":
        return (
            f"Hi {name},\n\n"
            "*URGENT REMINDER*\n\n"
            f"Your *{course}* course on OYE is still pending "
            f"(Status: *{status}*).\n\n"
            "Please complete it immediately. This is mandatory."
        )

    return (
        f"Hi {name},\n\n"
        f"Your *{course}* course on OYE is currently showing as "
        f"*{status}*.\n\n"
        "Please complete the course as soon as possible. "
        "This is mandatory."
    )


def build_training_message(
    name,
    training_name,
    training_date,
    training_time,
    venue,
    training_type,
    custom_template,
):
    if clean_text(custom_template):
        return render_template(
            custom_template,
            {
                "name": name,
                "training_name": training_name,
                "training_date": training_date,
                "training_time": training_time,
                "venue": venue,
                "type": training_type,
            },
        )

    details = []

    if clean_text(training_name):
        details.append(f"*Training:* {training_name}")

    if clean_text(training_type):
        details.append(f"*Category:* {training_type}")

    if clean_text(training_date):
        details.append(f"*Date:* {training_date}")

    if clean_text(training_time):
        details.append(f"*Time:* {training_time}")

    if clean_text(venue):
        details.append(f"*Venue/Link:* {venue}")

    return (
        f"Hi {name},\n\n"
        "This is a reminder that you have a training session coming up.\n\n"
        + "\n".join(details)
        + "\n\nEveryone should join the training on time."
    )


def make_whatsapp_url(phone, message):
    return (
        "https://web.whatsapp.com/send"
        f"?phone={quote(str(phone))}"
        f"&text={quote(message)}"
    )


def campaign_hash(*parts):
    raw = "||".join(clean_text(part) for part in parts)
    return hashlib.sha1(
        raw.encode("utf-8")
    ).hexdigest()[:16]


def safe_filename(value):
    value = re.sub(
        r"[^A-Za-z0-9_.-]+",
        "_",
        clean_text(value),
    )

    return value.strip("_") or "reminder"


@st.cache_data(show_spinner=False)
def read_excel_bytes(file_bytes):
    return pd.read_excel(
        BytesIO(file_bytes)
    )


@st.cache_data(show_spinner=False)
def read_csv_bytes(file_bytes):
    return pd.read_csv(
        BytesIO(file_bytes)
    )


def read_uploaded_table(uploaded):
    if uploaded.name.lower().endswith(".csv"):
        return read_csv_bytes(uploaded.getvalue())

    return read_excel_bytes(uploaded.getvalue())


def reusable_whatsapp_button(url, label):
    """
    Only ONE WhatsApp opener exists for the selected queue person.
    The same named target is reused for each next person.
    """
    safe_url = html.escape(
        url,
        quote=True,
    )

    safe_label = html.escape(label)

    link = (
        f'<a class="wa-open-button" '
        f'href="{safe_url}" '
        f'target="oye_whatsapp_reminder_window">'
        f'{safe_label}</a>'
    )

    st.markdown(
        link,
        unsafe_allow_html=True,
    )


# ============================================================
# SESSION STATE
# ============================================================

DEFAULTS = {
    "campaign_key": None,
    "batch_number": 0,
    "queue_index": 0,
    "sent_ids": set(),
    "skipped_ids": set(),
}

for state_key, state_value in DEFAULTS.items():
    if state_key not in st.session_state:
        st.session_state[state_key] = state_value


def reset_campaign(key):
    if st.session_state.campaign_key != key:
        st.session_state.campaign_key = key
        st.session_state.batch_number = 0
        st.session_state.queue_index = 0
        st.session_state.sent_ids = set()
        st.session_state.skipped_ids = set()


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:
    st.header("Reminder Hub")

    mode = st.radio(
        "Choose campaign",
        [
            "OYE Course Reminder",
            "Training Reminder",
        ],
    )

    st.divider()

    if mode == "OYE Course Reminder":
        st.markdown("""
**OYE Course Reminder**

1. Upload the latest OYE Excel.
2. Select your trainer.
3. Select the automatically detected course.
4. See 10 pending OECs in each batch.
5. Select one person from the queue.
6. Open the personalized WhatsApp draft.
7. Manually click Send.
8. Mark as sent.
9. Move to the next person or batch.
""")
    else:
        st.markdown("""
**Training Reminder**

1. Upload participant Excel/CSV.
2. Optionally upload a poster/image.
3. Enter training details.
4. Filter GT / MT / OPC if available.
5. Prepare personalized reminders.
6. Work through batches of 10.
7. Attach the poster manually in WhatsApp if needed.
""")

    st.divider()

    st.caption(
        "Names and course/training details are personalized automatically. "
        "WhatsApp Web URL drafts can prefill text, but they cannot "
        "automatically attach and send an image."
    )


# ============================================================
# HEADER
# ============================================================

st.title("OYE & Training Reminder Hub")

st.caption(
    "Excel/CSV reminders • Personalized names • Automatic course detection • "
    "10-person batches • WhatsApp Web queue"
)


# ============================================================
# OYE COURSE REMINDER MODE
# ============================================================

if mode == "OYE Course Reminder":

    uploaded_file = st.file_uploader(
        "Upload latest OYE Excel",
        type=["xlsx", "xls"],
        key="oye_upload",
    )

    if uploaded_file is None:
        st.info(
            "Upload the latest OYE Excel report to start."
        )
        st.stop()

    try:
        raw = read_uploaded_table(
            uploaded_file
        )
    except Exception as error:
        st.error(
            f"Could not read the Excel file: {error}"
        )
        st.stop()

    name_col = find_column(
        raw,
        NAME_CANDIDATES,
    )

    phone_col = find_column(
        raw,
        PHONE_CANDIDATES,
    )

    trainer_col = find_column(
        raw,
        TRAINER_CANDIDATES,
    )

    type_col = find_column(
        raw,
        TYPE_CANDIDATES,
    )

    missing = []

    if not name_col:
        missing.append("Employee/OEC name")

    if not phone_col:
        missing.append("Mobile number")

    if not trainer_col:
        missing.append("Trainer name")

    if missing:
        st.error(
            "Could not detect: "
            + ", ".join(missing)
        )

        st.caption(
            "Detected columns: "
            + ", ".join(
                map(str, raw.columns)
            )
        )

        st.stop()

    courses = get_course_columns(
        raw
    )

    trainers = sorted(
        raw[trainer_col]
        .dropna()
        .astype(str)
        .str.strip()
        .loc[
            lambda series: series != ""
        ]
        .unique()
        .tolist()
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

    c1, c2, c3 = st.columns(3)

    with c1:
        trainer = st.selectbox(
            "Select your trainer name",
            trainers,
        )

    with c2:
        course = st.selectbox(
            "Detected course",
            courses,
            help=(
                "New course columns in the uploaded "
                "OYE Excel are detected automatically."
            ),
        )

    with c3:
        reminder_level = st.selectbox(
            "Reminder type",
            [
                "First Reminder",
                "Second Reminder",
                "Final / Urgent Reminder",
            ],
        )

    custom_template = st.text_area(
        "Optional custom message template",
        placeholder=(
            "Hi {name}, your *{course}* course is "
            "{status}. Please complete it today."
        ),
        help=(
            "Write the template once. "
            "{name}, {course}, and {status} are automatically "
            "replaced for every OEC."
        ),
        height=120,
    )

    data = raw[
        raw[trainer_col]
        .astype(str)
        .str.strip()
        .eq(trainer)
    ].copy()

    if type_col:
        type_values = sorted(
            data[type_col]
            .dropna()
            .astype(str)
            .str.strip()
            .unique()
            .tolist()
        )

        selected_types = st.multiselect(
            "Filter by Type/Group (optional)",
            type_values,
            default=type_values,
        )

        if selected_types:
            data = data[
                data[type_col]
                .astype(str)
                .str.strip()
                .isin(selected_types)
            ].copy()

    data["OEC Name"] = data[
        name_col
    ].apply(
        lambda value: split_name_emp(value)[0]
    )

    data["Employee ID"] = data.apply(
        lambda row: get_employee_id(
            row,
            name_col,
        ),
        axis=1,
    )

    data["Course Status"] = data[
        course
    ].apply(
        get_course_status
    )

    phone_cleaned = data[
        phone_col
    ].apply(
        clean_phone
    )

    data["WhatsApp Phone"] = phone_cleaned.apply(
        lambda item: item[0]
    )

    data["Valid Number"] = phone_cleaned.apply(
        lambda item: item[1]
    )

    data["Unique ID"] = data.apply(
        lambda row: (
            clean_text(row["Employee ID"])
            or (
                clean_text(row["OEC Name"])
                + "-"
                + clean_text(
                    row.get(
                        phone_col,
                        "",
                    )
                )
            )
        ),
        axis=1,
    )

    data["Reminder Message"] = data.apply(
        lambda row: build_oye_message(
            row["OEC Name"],
            course,
            row["Course Status"],
            reminder_level,
            custom_template,
        ),
        axis=1,
    )

    pending = data[
        ~data["Course Status"]
        .apply(is_completed)
    ].copy()

    pending = pending.reset_index(
        drop=True
    )

    campaign_key = campaign_hash(
        "oye",
        uploaded_file.name,
        trainer,
        course,
        reminder_level,
        custom_template,
        "|".join(
            pending["Unique ID"]
            .astype(str)
            .tolist()
        ),
    )

    reset_campaign(
        campaign_key
    )

    total = len(pending)

    valid = (
        int(
            pending["Valid Number"].sum()
        )
        if total
        else 0
    )

    m1, m2, m3, m4 = st.columns(4)

    m1.metric(
        "Pending OECs",
        total,
    )

    m2.metric(
        "Valid WhatsApp Numbers",
        valid,
    )

    m3.metric(
        "Numbers Not Updated",
        total - valid,
    )

    m4.metric(
        "Sent in Session",
        len(
            st.session_state.sent_ids
        ),
    )

    if total == 0:
        st.success(
            f"All OECs for *{course}* are completed."
        )
        st.stop()

    preview = pending.copy()

    preview["Phone Status"] = preview[
        "Valid Number"
    ].map(
        {
            True: "Number Updated",
            False: "Number Not Updated in System",
        }
    )

    st.dataframe(
        preview[
            [
                "OEC Name",
                "Employee ID",
                "Course Status",
                "Phone Status",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )


# ============================================================
# TRAINING REMINDER MODE
# ============================================================

else:

    st.subheader(
        "Training Reminder"
    )

    uploaded_file = st.file_uploader(
        "Upload participant Excel or CSV",
        type=[
            "xlsx",
            "xls",
            "csv",
        ],
        key="training_upload",
    )

    image_file = st.file_uploader(
        "Optional training poster / image",
        type=[
            "png",
            "jpg",
            "jpeg",
            "webp",
        ],
        key="training_image",
    )

    left, right = st.columns(2)

    with left:
        training_name = st.text_input(
            "Training name"
        )

        training_date = st.text_input(
            "Training date",
            placeholder="Example: 24 August 2026",
        )

        training_time = st.text_input(
            "Training time",
            placeholder="Example: 10:00 AM",
        )

    with right:
        venue = st.text_input(
            "Venue / meeting link"
        )

        training_type = st.text_input(
            "Training category / group",
            placeholder="Example: GT, MT, OPC",
        )

    training_template = st.text_area(
        "Optional custom training message",
        placeholder=(
            "Hi {name},\n\n"
            "Reminder: You have *{training_name}* "
            "on {training_date} at {training_time}. "
            "Venue/Link: {venue}.\n\n"
            "Everyone should join on time."
        ),
        help=(
            "Available placeholders: "
            "{name}, {training_name}, {training_date}, "
            "{training_time}, {venue}, {type}"
        ),
        height=150,
    )

    if image_file is not None:
        st.image(
            image_file,
            caption="Training poster/image preview",
            width=420,
        )

    if uploaded_file is None:
        st.info(
            "Upload the participant list. The app needs "
            "a name and mobile number. A Type/Group column "
            "is optional."
        )
        st.stop()

    try:
        raw = read_uploaded_table(
            uploaded_file
        )
    except Exception as error:
        st.error(
            f"Could not read the participant file: {error}"
        )
        st.stop()

    name_col = find_column(
        raw,
        NAME_CANDIDATES,
    )

    phone_col = find_column(
        raw,
        PHONE_CANDIDATES,
    )

    type_col = find_column(
        raw,
        TYPE_CANDIDATES,
    )

    missing = []

    if not name_col:
        missing.append("Name")

    if not phone_col:
        missing.append("Mobile number")

    if missing:
        st.error(
            "Could not detect: "
            + ", ".join(missing)
        )

        st.caption(
            "Detected columns: "
            + ", ".join(
                map(str, raw.columns)
            )
        )

        st.stop()

    data = raw.copy()

    data["OEC Name"] = data[
        name_col
    ].apply(
        lambda value: split_name_emp(value)[0]
    )

    data["Employee ID"] = data.apply(
        lambda row: get_employee_id(
            row,
            name_col,
        ),
        axis=1,
    )

    phone_cleaned = data[
        phone_col
    ].apply(
        clean_phone
    )

    data["WhatsApp Phone"] = phone_cleaned.apply(
        lambda item: item[0]
    )

    data["Valid Number"] = phone_cleaned.apply(
        lambda item: item[1]
    )

    if type_col:
        type_values = sorted(
            data[type_col]
            .dropna()
            .astype(str)
            .str.strip()
            .unique()
            .tolist()
        )

        selected_types = st.multiselect(
            "Send to selected Type/Group",
            type_values,
            default=type_values,
        )

        if selected_types:
            data = data[
                data[type_col]
                .astype(str)
                .str.strip()
                .isin(selected_types)
            ].copy()

        data["Type / Group"] = data[
            type_col
        ].astype(str).str.strip()

    else:
        data["Type / Group"] = ""

    data["Unique ID"] = data.apply(
        lambda row: (
            clean_text(row["Employee ID"])
            or (
                clean_text(row["OEC Name"])
                + "-"
                + clean_text(
                    row.get(
                        phone_col,
                        "",
                    )
                )
            )
        ),
        axis=1,
    )

    data["Reminder Message"] = data.apply(
        lambda row: build_training_message(
            row["OEC Name"],
            training_name,
            training_date,
            training_time,
            venue,
            (
                row["Type / Group"]
                or training_type
            ),
            training_template,
        ),
        axis=1,
    )

    pending = data.reset_index(
        drop=True
    )

    campaign_key = campaign_hash(
        "training",
        uploaded_file.name,
        training_name,
        training_date,
        training_time,
        venue,
        training_type,
        training_template,
        "|".join(
            pending["Unique ID"]
            .astype(str)
            .tolist()
        ),
    )

    reset_campaign(
        campaign_key
    )

    total = len(pending)

    valid = (
        int(
            pending["Valid Number"].sum()
        )
        if total
        else 0
    )

    m1, m2, m3 = st.columns(3)

    m1.metric(
        "Participants",
        total,
    )

    m2.metric(
        "Valid WhatsApp Numbers",
        valid,
    )

    m3.metric(
        "Numbers Not Updated",
        total - valid,
    )

    if image_file is not None:
        st.warning(
            "The app supports image upload and preview. "
            "However, standard WhatsApp Web draft URLs can prefill "
            "text only; the image must be attached manually in each chat."
        )


# ============================================================
# COMMON 10-PERSON BATCH QUEUE
# ============================================================

if len(pending) == 0:
    st.info(
        "No people available in this campaign."
    )
    st.stop()

total_batches = math.ceil(
    len(pending) / BATCH_SIZE
)

if st.session_state.batch_number >= total_batches:
    st.session_state.batch_number = (
        total_batches - 1
    )

batch_start = (
    st.session_state.batch_number
    * BATCH_SIZE
)

batch_end = min(
    batch_start + BATCH_SIZE,
    len(pending),
)

batch = pending.iloc[
    batch_start:batch_end
].copy().reset_index(
    drop=True
)

if st.session_state.queue_index >= len(batch):
    st.session_state.queue_index = 0

st.divider()

nav1, nav2, nav3 = st.columns(
    [1, 2, 1]
)

with nav1:
    if st.button(
        "← Previous Batch",
        disabled=(
            st.session_state.batch_number == 0
        ),
        use_container_width=True,
    ):
        st.session_state.batch_number -= 1
        st.session_state.queue_index = 0
        st.rerun()

with nav2:
    st.markdown(
        f"<div style='text-align:center;"
        f"padding-top:8px;font-weight:600;'>"
        f"Batch {st.session_state.batch_number + 1} "
        f"of {total_batches} • "
        f"Showing {len(batch)} people"
        f"</div>",
        unsafe_allow_html=True,
    )

with nav3:
    if st.button(
        "Next Batch →",
        disabled=(
            st.session_state.batch_number
            >= total_batches - 1
        ),
        use_container_width=True,
    ):
        st.session_state.batch_number += 1
        st.session_state.queue_index = 0
        st.rerun()


st.subheader(
    f"Current Batch – {len(batch)} People"
)

# All 10 people are visible as a queue.
queue_options = []

for index, row in batch.iterrows():
    sent = (
        row["Unique ID"]
        in st.session_state.sent_ids
    )

    phone_status = (
        "Ready"
        if row["Valid Number"]
        else "Number missing"
    )

    status = (
        "✓ Sent"
        if sent
        else phone_status
    )

    queue_options.append(
        f"{index + 1}. {row['OEC Name']} — {status}"
    )


selected_label = st.radio(
    "Select the person whose WhatsApp draft you want to prepare",
    queue_options,
    index=st.session_state.queue_index,
    key=(
        f"queue_selector_"
        f"{st.session_state.batch_number}"
    ),
)

selected_index = queue_options.index(
    selected_label
)

st.session_state.queue_index = selected_index

current = batch.iloc[
    selected_index
]


# ============================================================
# DISPLAY ALL 10 PEOPLE
# ============================================================

for index, row in batch.iterrows():

    sent = (
        row["Unique ID"]
        in st.session_state.sent_ids
    )

    state = (
        "✓ Sent"
        if sent
        else (
            "Ready"
            if row["Valid Number"]
            else "Number Not Updated"
        )
    )

    extra = ""

    if mode == "OYE Course Reminder":
        extra = (
            " • Status: "
            + html.escape(
                clean_text(
                    row["Course Status"]
                )
            )
        )

    elif clean_text(
        row.get(
            "Type / Group",
            "",
        )
    ):
        extra = (
            " • "
            + html.escape(
                clean_text(
                    row["Type / Group"]
                )
            )
        )

    st.markdown(
        f"""
<div class="reminder-card">
<b>{index + 1}. {html.escape(clean_text(row['OEC Name']))}</b>
<span class="small-muted">
 • ID: {html.escape(clean_text(row['Employee ID']) or 'Not available')}
 {extra}
</span>
<br>
<span class="small-muted">{html.escape(state)}</span>
</div>
""",
        unsafe_allow_html=True,
    )


# ============================================================
# ONE WHATSAPP OPENER
# ============================================================

st.divider()

st.subheader(
    "WhatsApp Batch Queue"
)

status_text = (
    "✓ Number Updated"
    if current["Valid Number"]
    else "Number Not Updated in System"
)

st.markdown(
    f"""
<div class="queue-box">
<b>Draft {selected_index + 1} of {len(batch)}</b>
<br>
<span class="small-muted">
Name: {html.escape(clean_text(current['OEC Name']))}
 • {html.escape(status_text)}
</span>
</div>
""",
    unsafe_allow_html=True,
)

if current["Valid Number"]:

    wa_url = make_whatsapp_url(
        current["WhatsApp Phone"],
        current["Reminder Message"],
    )

    reusable_whatsapp_button(
        wa_url,
        "Open / Reuse WhatsApp Web Draft",
    )

    st.caption(
        "Only one WhatsApp opener is shown for the selected queue person. "
        "Select the next person and use the same button again."
    )

    with st.expander(
        "Preview current personalized message"
    ):
        st.code(
            current["Reminder Message"],
            language=None,
        )

else:

    st.error(
        "Number Not Updated in System"
    )

    original = clean_text(
        current.get(
            phone_col,
            "",
        )
    )

    if original:
        st.caption(
            f"Current Excel value: {original}"
        )

    st.info(
        "Update the mobile number in the source Excel "
        "and upload it again."
    )


action1, action2, action3 = st.columns(3)

with action1:
    if st.button(
        "✓ Mark as Sent",
        disabled=(
            not current["Valid Number"]
        ),
        use_container_width=True,
    ):
        st.session_state.sent_ids.add(
            current["Unique ID"]
        )

        st.success(
            f"{current['OEC Name']} marked as sent."
        )

with action2:
    if st.button(
        "Skip / Not Sent",
        use_container_width=True,
    ):
        st.session_state.skipped_ids.add(
            current["Unique ID"]
        )

        st.warning(
            f"{current['OEC Name']} marked as not sent."
        )

with action3:
    if st.button(
        "Next Person →",
        disabled=(
            selected_index
            >= len(batch) - 1
        ),
        use_container_width=True,
    ):
        st.session_state.queue_index = min(
            selected_index + 1,
            len(batch) - 1,
        )

        st.rerun()


# ============================================================
# SESSION REPORT
# ============================================================

st.divider()

st.subheader(
    "Campaign Session Report"
)

report = pending.copy()

report["Session Status"] = report[
    "Unique ID"
].apply(
    lambda value: (
        "Sent"
        if value
        in st.session_state.sent_ids
        else (
            "Not Sent"
            if value
            in st.session_state.skipped_ids
            else "Pending"
        )
    )
)

sent_count = int(
    (
        report["Session Status"]
        == "Sent"
    ).sum()
)

not_sent_count = int(
    (
        report["Session Status"]
        == "Not Sent"
    ).sum()
)

pending_count = int(
    (
        report["Session Status"]
        == "Pending"
    ).sum()
)

r1, r2, r3 = st.columns(3)

r1.metric(
    "Sent",
    sent_count,
)

r2.metric(
    "Not Sent",
    not_sent_count,
)

r3.metric(
    "Still Pending",
    pending_count,
)

export_columns = [
    column
    for column in [
        "OEC Name",
        "Employee ID",
        "WhatsApp Phone",
        "Valid Number",
        "Course Status",
        "Type / Group",
        "Reminder Message",
        "Session Status",
    ]
    if column
    in report.columns
]

csv_bytes = report[
    export_columns
].to_csv(
    index=False
).encode(
    "utf-8-sig"
)

st.download_button(
    "Download Campaign Report (CSV)",
    data=csv_bytes,
    file_name=(
        f"{safe_filename(mode)}_campaign_"
        f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    ),
    mime="text/csv",
    use_container_width=True,
)

st.caption(
    "Important: one WhatsApp Web tab can display one chat at a time. "
    "This app therefore uses a 10-person queue: all 10 people are visible, "
    "but drafts are opened sequentially using one named WhatsApp target. "
    "A normal web link cannot keep ten different unsent chats drafted "
    "inside one WhatsApp screen at the same time."
)
