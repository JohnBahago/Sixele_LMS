PERMISSION_CATALOG = [
    ("users", "View"), ("users", "Create"), ("users", "Edit"), ("users", "Delete"), ("users", "Manage"),
    ("courses", "View"), ("courses", "Create"), ("courses", "Edit"), ("courses", "Delete"), ("courses", "Publish"), ("courses", "Archive"),
    ("modules", "View"), ("modules", "Create"), ("modules", "Edit"), ("modules", "Delete"),
    ("lessons", "View"), ("lessons", "Create"), ("lessons", "Edit"), ("lessons", "Delete"),
    ("activities", "View"), ("activities", "Create"), ("activities", "Edit"), ("activities", "Delete"), ("activities", "Assess"),
    ("assignments", "View"), ("assignments", "Create"), ("assignments", "Edit"), ("assignments", "Delete"), ("assignments", "Grade"),
    ("assessments", "View"), ("assessments", "Create"), ("assessments", "Edit"), ("assessments", "Delete"), ("assessments", "Grade"), ("assessments", "Manage Rubrics"),
    ("submissions", "View"), ("submissions", "Review"), ("submissions", "Approve"), ("submissions", "Return for Revision"), ("submissions", "Grade"),
    ("enrollments", "View"), ("enrollments", "Create"), ("enrollments", "Edit"), ("enrollments", "Cancel"), ("enrollments", "Manage"),
    ("instructors", "View"), ("instructors", "Assign"), ("instructors", "Edit"), ("instructors", "Manage"),
    ("certificates", "View"), ("certificates", "Create"), ("certificates", "Manage"), ("certificates", "Issue"), ("certificates", "Revoke"), ("certificates", "Verify"), ("certificates", "Manage Templates"),
    ("reports", "View"), ("reports", "Export"),
    ("content", "View"), ("content", "Upload"), ("content", "Edit"), ("content", "Delete"), ("content", "Manage"),
    ("notifications", "View"), ("notifications", "Create"), ("notifications", "Manage"),
    ("settings", "View"), ("settings", "Edit"),
    ("audit", "View"), ("audit", "Export"),
    ("security", "View"), ("security", "Manage"),
    ("jobs", "View"), ("jobs", "Manage"),
    ("roles", "View"), ("roles", "Create"), ("roles", "Edit"), ("roles", "Delete"), ("roles", "Manage"),
    ("cohorts", "View"), ("cohorts", "Create"), ("cohorts", "Edit"), ("cohorts", "Delete"), ("cohorts", "Manage"),
    ("sessions", "View"), ("sessions", "Create"), ("sessions", "Edit"), ("sessions", "Delete"), ("sessions", "Manage"),
    ("attendance", "View"), ("attendance", "Manage"),
]

PERMISSIONS = [
    {"id": f"{resource}.{label.lower().replace(' ', '_')}", "group": resource.title(), "label": label}
    for resource, label in PERMISSION_CATALOG
]
PERMISSION_IDS = {p["id"] for p in PERMISSIONS}
