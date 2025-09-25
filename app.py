from flask import Flask, render_template, redirect, url_for, request, abort
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from datetime import datetime, timedelta

app = Flask(__name__)

# SQLite DB
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///theatre.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

app.jinja_env.globals.update(getattr=getattr)

# --- Database Model ---
class Case(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_name = db.Column(db.String(100), nullable=False)
    case_date = db.Column(db.Date, default=datetime.utcnow().date, nullable=False)


    # Times
    pushed_in = db.Column(db.DateTime, nullable=True)
    anaesthesia_start = db.Column(db.DateTime, nullable=True)
    surgical_prep = db.Column(db.DateTime, nullable=True)
    surgical_start = db.Column(db.DateTime, nullable=True)
    surgical_finish = db.Column(db.DateTime, nullable=True)
    anaesthesia_finish = db.Column(db.DateTime, nullable=True)
    pushed_out = db.Column(db.DateTime, nullable=True)

    # Delay reasons per step
    pushed_in_reason = db.Column(db.String(50), nullable=True)
    anaesthesia_start_reason = db.Column(db.String(50), nullable=True)
    surgical_prep_reason = db.Column(db.String(50), nullable=True)
    surgical_start_reason = db.Column(db.String(50), nullable=True)
    surgical_finish_reason = db.Column(db.String(50), nullable=True)
    anaesthesia_finish_reason = db.Column(db.String(50), nullable=True)
    pushed_out_reason = db.Column(db.String(50), nullable=True)

    # Delay explanations per step
    pushed_in_reason_text = db.Column(db.String(255))
    anaesthesia_start_reason_text = db.Column(db.String(255))
    surgical_prep_reason_text = db.Column(db.String(255))
    surgical_start_reason_text = db.Column(db.String(255))
    surgical_finish_reason_text = db.Column(db.String(255))
    anaesthesia_finish_reason_text = db.Column(db.String(255))
    pushed_out_reason_text = db.Column(db.String(255))

# --- Routes ---
@app.route('/', defaults={'date_str': None})
@app.route('/cases/<date_str>')
def case_list(date_str):
    if date_str:
        try:
            current_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            current_date = datetime.today().date()
    else:
        current_date = datetime.today().date()

    prev_date = current_date - timedelta(days=1)
    next_date = current_date + timedelta(days=1)

    cases = (
        Case.query
        .filter(func.date(Case.case_date) == current_date)
        .order_by(Case.id)
        .all()
    )

    return render_template(
        'case_list.html',
        cases=cases,
        current_date=current_date,
        prev_date=prev_date,
        next_date=next_date,
        today=datetime.today().date()   # 👈 pass today separately
    )


@app.route('/case/<int:case_id>', methods=['GET', 'POST'])
def case_view(case_id):
    case = Case.query.get_or_404(case_id)

    fields = [
        ("Pushed In", "pushed_in"),
        ("Anaesthesia Start", "anaesthesia_start"),
        ("Surgical Prep", "surgical_prep"),
        ("Surgical Start", "surgical_start"),
        ("Surgical Finish", "surgical_finish"),
        ("Anaesthesia Finish", "anaesthesia_finish"),
        ("Pushed Out", "pushed_out"),
    ]

    if request.method == 'POST':
        action = request.form.get('action')

        # update times from inputs
        for label, field_name in fields:
            time_str = request.form.get(f"time_{field_name}")
            if time_str:
                new_time = datetime.combine(datetime.today(), datetime.strptime(time_str, "%H:%M").time())
                setattr(case, field_name, new_time)

            reason = request.form.get(f"reason_{field_name}")
            explanation = request.form.get(f"reason_text_{field_name}")
            if reason is not None:
                setattr(case, f"{field_name}_reason", reason)
                setattr(case, f"{field_name}_reason_text", explanation)

        # validate chronological order
        order = ["pushed_in", "anaesthesia_start", "surgical_prep",
                 "surgical_start", "surgical_finish",
                 "anaesthesia_finish", "pushed_out"]

        last_time = None
        for field in order:
            current = getattr(case, field)
            if current:
                if last_time and current < last_time:
                    flash(f"Invalid sequence: {field.replace('_', ' ').title()} occurs before previous step.")
                    return redirect(url_for('case_view', case_id=case.id))
                last_time = current

        db.session.commit()
        return redirect(url_for('case_view', case_id=case.id))

    return render_template("case.html", case=case, fields=fields)

@app.route('/new', methods=['POST'])
def new_case():
    patient_name = request.form.get('patient_name')
    case_date = datetime.today().date()
    new_case = Case(patient_name=patient_name, case_date=case_date)
    db.session.add(new_case)
    db.session.commit()
    return redirect(url_for('case_list'))

@app.route('/dashboard')
@app.route('/dashboard')
def dashboard():
    today = datetime.today().date()
    start_of_week = today - timedelta(days=today.weekday())
    start_of_month = today.replace(day=1)

    daily_cases = Case.query.filter(func.date(Case.case_date) == today).all()
    weekly_cases = Case.query.filter(func.date(Case.case_date) >= start_of_week).all()
    monthly_cases = Case.query.filter(func.date(Case.case_date) >= start_of_month).all()

    def compute_intervals(cases):
        intervals = []
        for case in cases:
            intervals.append({
                "patient": case.patient_name,
                "pushed_in_to_anaesthesia": (case.anaesthesia_start - case.pushed_in).total_seconds()/60 if case.anaesthesia_start and case.pushed_in else None,
                "anaesthesia_to_surgical_start": (case.surgical_start - case.anaesthesia_start).total_seconds()/60 if case.surgical_start and case.anaesthesia_start else None,
                "surgical_duration": (case.surgical_finish - case.surgical_start).total_seconds()/60 if case.surgical_finish and case.surgical_start else None,
                "surgical_finish_to_anaesthesia_finish": (case.anaesthesia_finish - case.surgical_finish).total_seconds()/60 if case.anaesthesia_finish and case.surgical_finish else None,
                "anaesthesia_finish_to_pushed_out": (case.pushed_out - case.anaesthesia_finish).total_seconds()/60 if case.pushed_out and case.anaesthesia_finish else None
            })
        return intervals

    daily_intervals = compute_intervals(daily_cases)
    weekly_intervals = compute_intervals(weekly_cases)
    monthly_intervals = compute_intervals(monthly_cases)

    def extract_reasons(cases):
        summary = {"Staff": [], "Equipment": [], "Process": [], "Other": []}
        fields = [
            "pushed_in", "anaesthesia_start", "surgical_prep",
            "surgical_start", "surgical_finish", "anaesthesia_finish", "pushed_out"
        ]

        for case in cases:
            for field in fields:
                reason = getattr(case, f"{field}_reason", None)
                explanation = getattr(case, f"{field}_reason_text", None)
                if reason in summary:
                    entry = f"{case.patient_name} ({field.replace('_', ' ').title()})"
                    if explanation:
                        entry += f": {explanation}"
                    summary[reason].append(entry)

        # Filter out empty reason groups
        return {k: v for k, v in summary.items() if v}

    daily_reasons = extract_reasons(daily_cases)
    weekly_reasons = extract_reasons(weekly_cases)
    monthly_reasons = extract_reasons(monthly_cases)

    return render_template(
        'dashboard.html',
        daily_intervals=daily_intervals,
        weekly_intervals=weekly_intervals,
        monthly_intervals=monthly_intervals,
        daily_reasons=daily_reasons,
        weekly_reasons=weekly_reasons,
        monthly_reasons=monthly_reasons
    )

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
