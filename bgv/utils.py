import frappe

def get_bgv_settings():
    settings = frappe.get_single("BGV Settings")

    return {
        "account": settings.account,
        "username": settings.username,
        "password": settings.get_password("password"),
        "mode": settings.mode,
        "endpoint": settings.endpoint_url
    }