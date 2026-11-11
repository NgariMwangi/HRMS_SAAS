from datetime import date


def upcoming_birthday(born: date, today: date) -> date:
    for year in (today.year, today.year + 1):
        try:
            birthday = born.replace(year=year)
        except ValueError:
            birthday = date(year, 3, 1)
        if birthday >= today:
            return birthday
    raise ValueError("Could not determine next birthday")


def employee_alerts(employees, today: date, legacy_ends=None):
    birthdays, probation = [], []
    for employee in employees:
        if employee.status != "ACTIVE":
            continue
        person = {"employee_id": str(employee.id), "name": " ".join(filter(None, [employee.first_name, employee.other_names, employee.last_name])), "branch_id": str(employee.branch_id)}
        if employee.date_of_birth:
            birthday = upcoming_birthday(employee.date_of_birth, today)
            days = (birthday - today).days
            if days <= 14:
                birthdays.append({**person, "date": birthday, "days": days})
        if employee.employment_type == "PROBATION":
            end = employee.date_ended or (legacy_ends or {}).get(str(employee.id))
            if end and (end - today).days <= 14:
                probation.append({**person, "date": end, "days": (end - today).days})
    key = lambda row: (row["days"], row["name"].casefold())
    return {"as_of": today, "window_days": 14, "birthdays": sorted(birthdays, key=key), "probation": sorted(probation, key=key)}
