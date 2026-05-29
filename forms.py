from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (
    StringField,
    PasswordField,
    SubmitField,
    TextAreaField,
    BooleanField,
    SelectField,
    DateField,
    IntegerField
)
from wtforms.validators import (
    DataRequired,
    Email,
    Length,
    Optional,
    URL,
    Regexp,
    NumberRange
)


class LoginForm(FlaskForm):
    email = StringField(
        "Email",
        validators=[DataRequired(), Email()]
    )

    password = PasswordField(
        "Password",
        validators=[DataRequired()]
    )

    submit = SubmitField("Log in")


class TenantSettingsForm(FlaskForm):
    tenant_slug = StringField(
        "Website slug",
        validators=[
            DataRequired(),
            Length(min=3, max=120),
            Regexp(
                r"^[a-z0-9-]+$",
                message="Use lowercase letters, numbers and hyphens only."
            )
        ],
        description="Example: fiona-godfrey-hr"
    )

    business_name = StringField(
        "Business name",
        validators=[DataRequired(), Length(max=255)]
    )

    strapline = StringField(
        "Strapline",
        validators=[Optional(), Length(max=255)]
    )

    logo = FileField(
        "Logo",
        validators=[
            Optional(),
            FileAllowed(["jpg", "jpeg", "png", "webp"], "Images only.")
        ]
    )

    primary_colour = StringField(
        "Primary colour",
        validators=[
            DataRequired(),
            Regexp(
                r"^#[0-9A-Fa-f]{6}$",
                message="Use a valid hex colour, e.g. #005b5a."
            )
        ],
        default="#005b5a"
    )

    accent_colour = StringField(
        "Accent colour",
        validators=[
            DataRequired(),
            Regexp(
                r"^#[0-9A-Fa-f]{6}$",
                message="Use a valid hex colour, e.g. #f5b041."
            )
        ],
        default="#f5b041"
    )

    text_colour = StringField(
        "Text colour",
        validators=[
            DataRequired(),
            Regexp(
                r"^#[0-9A-Fa-f]{6}$",
                message="Use a valid hex colour, e.g. #1f2937."
            )
        ],
        default="#1f2937"
    )

    website_intro = TextAreaField(
        "Website intro",
        validators=[Optional()]
    )

    about_text = TextAreaField(
        "About your consultancy",
        validators=[Optional()]
    )

    services_text = TextAreaField(
        "Services offered",
        validators=[Optional()]
    )

    sectors_text = TextAreaField(
        "Sector experience",
        validators=[Optional()]
    )

    contact_email = StringField(
        "Contact email",
        validators=[Optional(), Email()]
    )

    contact_phone = StringField(
        "Contact phone",
        validators=[Optional(), Length(max=100)]
    )

    linkedin_url = StringField(
        "LinkedIn URL",
        validators=[Optional(), URL()]
    )

    cta_label = StringField(
        "Call-to-action button text",
        validators=[Optional(), Length(max=100)],
        default="Book a discovery call"
    )

    cta_url = StringField(
        "Call-to-action URL",
        validators=[Optional(), URL()]
    )

    is_published = BooleanField("Publish website")

    submit = SubmitField("Save website settings")


class ResourceForm(FlaskForm):
    title = StringField(
        "Resource title",
        validators=[DataRequired(), Length(max=255)]
    )

    category = SelectField(
        "Category",
        choices=[
            ("Employee Relations", "Employee Relations"),
            ("Recruitment", "Recruitment"),
            ("Contracts and Onboarding", "Contracts and Onboarding"),
            ("Policies and Handbooks", "Policies and Handbooks"),
            ("Redundancy and Restructure", "Redundancy and Restructure"),
            ("Performance and Capability", "Performance and Capability"),
            ("Absence Management", "Absence Management"),
            ("Consultant Business Tools", "Consultant Business Tools"),
            ("HIVE Covered", "HIVE Covered"),
            ("Other", "Other"),
        ],
        validators=[DataRequired()]
    )

    description = TextAreaField(
        "Description",
        validators=[Optional()]
    )

    resource_file = FileField(
        "Resource file",
        validators=[
            Optional(),
            FileAllowed(
                ["pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt"],
                "Allowed files: PDF, Word, Excel, PowerPoint or TXT."
            )
        ]
    )

    required_tier = SelectField(
        "Required tier",
        choices=[
            ("free", "Free"),
            ("starter", "Starter"),
            ("professional", "Professional"),
            ("covered", "Covered"),
            ("boutique", "Boutique"),
        ],
        default="starter",
        validators=[DataRequired()]
    )

    consultant_notes = TextAreaField(
        "Consultant delivery notes",
        validators=[Optional()]
    )

    risk_flags = TextAreaField(
        "Risk flags",
        validators=[Optional()]
    )

    escalation_points = TextAreaField(
        "Escalation points",
        validators=[Optional()]
    )

    is_active = BooleanField("Active")

    submit = SubmitField("Save resource")


class CoverRequestForm(FlaskForm):
    cover_type = SelectField(
        "Cover type",
        choices=[
            ("holiday", "Holiday cover"),
            ("sickness", "Sickness cover"),
            ("overflow", "Overflow / capacity cover"),
            ("emergency", "Emergency cover"),
        ],
        validators=[DataRequired()]
    )

    start_date = DateField(
        "Start date",
        validators=[DataRequired()],
        format="%Y-%m-%d"
    )

    end_date = DateField(
        "End date",
        validators=[DataRequired()],
        format="%Y-%m-%d"
    )

    summary = TextAreaField(
        "Summary",
        validators=[Optional()],
        description="Briefly explain what cover is needed and any important context."
    )

    submit = SubmitField("Save cover request")


class CoverClientForm(FlaskForm):
    client_name = StringField(
        "Client name",
        validators=[DataRequired(), Length(max=255)]
    )

    contact_name = StringField(
        "Main contact name",
        validators=[Optional(), Length(max=255)]
    )

    contact_email = StringField(
        "Main contact email",
        validators=[Optional(), Email()]
    )

    contact_phone = StringField(
        "Main contact phone",
        validators=[Optional(), Length(max=100)]
    )

    retainer_scope = TextAreaField(
        "Retainer / service scope",
        validators=[Optional()]
    )

    authority_limits = TextAreaField(
        "Authority limits",
        validators=[Optional()],
        description="What can HIVE do or not do on your behalf?"
    )

    escalation_rules = TextAreaField(
        "Escalation rules",
        validators=[Optional()],
        description="When should HIVE escalate back to you, a senior advisor, or legal partner?"
    )

    open_issues = TextAreaField(
        "Open issues",
        validators=[Optional()],
        description="Current live matters, pending actions or expected enquiries."
    )

    risk_notes = TextAreaField(
        "Risk notes",
        validators=[Optional()],
        description="Known legal, employee relations, reputational or client relationship risks."
    )

    submit = SubmitField("Save covered client")


class AdminCoverStatusForm(FlaskForm):
    admin_notes = TextAreaField(
        "Admin notes",
        validators=[Optional()]
    )

    submit = SubmitField("Save notes")


class PeopleSignalLeadForm(FlaskForm):
    source_reference = StringField(
        "PeopleSignal reference",
        validators=[Optional(), Length(max=255)]
    )

    company_name = StringField(
        "Company name",
        validators=[DataRequired(), Length(max=255)]
    )

    contact_name = StringField(
        "Contact name",
        validators=[Optional(), Length(max=255)]
    )

    contact_email = StringField(
        "Contact email",
        validators=[Optional(), Email()]
    )

    contact_phone = StringField(
        "Contact phone",
        validators=[Optional(), Length(max=100)]
    )

    sector = StringField(
        "Sector",
        validators=[Optional(), Length(max=100)]
    )

    employee_count = SelectField(
        "Employee count",
        choices=[
            ("", "Not known"),
            ("1-10", "1-10"),
            ("11-25", "11-25"),
            ("26-50", "26-50"),
            ("51-100", "51-100"),
            ("101-250", "101-250"),
            ("250+", "250+"),
        ],
        validators=[Optional()]
    )

    location = StringField(
        "Location",
        validators=[Optional(), Length(max=255)]
    )

    signal_type = SelectField(
        "PeopleSignal type",
        choices=[
            ("pulse_survey", "Pulse survey"),
            ("hr_health_check", "HR health check"),
            ("engagement_diagnostic", "Engagement diagnostic"),
            ("exit_feedback", "Exit feedback"),
            ("manager_capability", "Manager capability diagnostic"),
            ("callback_request", "Callback request"),
            ("other", "Other"),
        ],
        validators=[DataRequired()]
    )

    signal_summary = TextAreaField(
        "Signal summary",
        validators=[Optional()]
    )

    support_needed = TextAreaField(
        "Support needed",
        validators=[Optional()]
    )

    urgency = SelectField(
        "Urgency",
        choices=[
            ("low", "Low"),
            ("medium", "Medium"),
            ("high", "High"),
            ("critical", "Critical"),
        ],
        default="medium",
        validators=[DataRequired()]
    )

    people_signal_score = IntegerField(
        "PeopleSignal score",
        validators=[Optional(), NumberRange(min=0, max=100)]
    )

    risk_level = SelectField(
        "Risk level",
        choices=[
            ("low", "Low"),
            ("medium", "Medium"),
            ("high", "High"),
            ("critical", "Critical"),
        ],
        default="medium",
        validators=[DataRequired()]
    )

    submit = SubmitField("Create PeopleSignal lead")


class AdminLeadForm(FlaskForm):
    assigned_consultant_id = SelectField(
        "Assign consultant",
        coerce=int,
        validators=[Optional()]
    )

    status = SelectField(
        "Lead status",
        choices=[
            ("new", "New"),
            ("qualified", "Qualified"),
            ("assigned", "Assigned"),
            ("accepted", "Accepted"),
            ("declined", "Declined"),
            ("won", "Won"),
            ("lost", "Lost"),
            ("closed", "Closed"),
        ],
        validators=[DataRequired()]
    )

    admin_notes = TextAreaField(
        "Admin notes",
        validators=[Optional()]
    )

    submit = SubmitField("Save lead")


class ConsultantLeadNotesForm(FlaskForm):
    consultant_notes = TextAreaField(
        "Consultant notes",
        validators=[Optional()]
    )

    submit = SubmitField("Save notes")


class ExpertRequestForm(FlaskForm):
    category = SelectField(
        "Category",
        choices=[
            ("Employee Relations", "Employee Relations"),
            ("Employment Law", "Employment Law"),
            ("TUPE", "TUPE"),
            ("Recruitment", "Recruitment"),
            ("Pay / Reward", "Pay / Reward"),
            ("Complex Absence", "Complex Absence"),
            ("Safeguarding", "Safeguarding"),
            ("Other", "Other"),
        ],
        validators=[DataRequired()]
    )

    urgency = SelectField(
        "Urgency",
        choices=[
            ("routine", "Routine"),
            ("urgent", "Urgent"),
            ("critical", "Critical"),
        ],
        default="routine",
        validators=[DataRequired()]
    )

    subject = StringField(
        "Subject",
        validators=[DataRequired(), Length(max=255)]
    )

    summary = TextAreaField(
        "Summary",
        validators=[Optional()]
    )

    desired_outcome = TextAreaField(
        "Desired outcome",
        validators=[Optional()]
    )

    submit = SubmitField("Submit expert request")


class AdminExpertRequestForm(FlaskForm):
    status = SelectField(
        "Status",
        choices=[
            ("new", "New"),
            ("reviewing", "Reviewing"),
            ("assigned", "Assigned"),
            ("responded", "Responded"),
            ("closed", "Closed"),
        ],
        validators=[DataRequired()]
    )

    admin_notes = TextAreaField(
        "Admin notes",
        validators=[Optional()]
    )

    response_summary = TextAreaField(
        "Response summary",
        validators=[Optional()]
    )

    submit = SubmitField("Save expert request")