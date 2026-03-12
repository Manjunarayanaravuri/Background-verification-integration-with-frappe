import frappe
import requests
import xml.etree.ElementTree as ET


@frappe.whitelist(allow_guest=True)
def place_bgv_order(employee):

    if not employee:
        frappe.throw("Employee is required")

    # Fetch BGV Settings
    settings = frappe.get_single("BGV Settings")

    # Fetch Employee details
    emp = frappe.get_doc("Employee", employee)

    # Create BGV Order doc
    doc = frappe.new_doc("BGV Order")
    doc.employee = employee
    doc.employee_name = emp.employee_name
    doc.status = "Order Initiated"
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    # Build postback types from settings
    postback_types = settings.postback_types or "IPC::IPV::OCR"

    # Format DOB safely
    dob = ""
    if emp.date_of_birth:
        dob = emp.date_of_birth.strftime("%Y%m%d")

    # Get employee name parts
    name_first = emp.first_name or ""
    name_middle = getattr(emp, "middle_name", "") or ""
    name_last = emp.last_name or ""

    # Get employee email
    emp_email = emp.personal_email or emp.company_email or ""

    frappe.log_error(
        f"Placing BGV Order for Employee: {employee}",
        "BGV Place Order Debug"
    )

    # Build XML payload
    xml_payload = f"""<?xml version="1.0" encoding="UTF-8"?>
<Accio_Order>

  <login>
    <account>{settings.account}</account>
    <username>{settings.username}</username>
    <password>{settings.get_password("password")}</password>
  </login>

  <mode>{settings.mode}</mode>

  <placeOrder>

    <package>Basic All</package>
    <IncludeDefaultProducts/>
    <preselect_all_included_products/>
    <IncludePreselectedProducts/>

    <orderInfo>
      <requester_name>{frappe.session.user}</requester_name>
      <requester_email>{frappe.session.user}</requester_email>
      <requester_phone>111-111-1111</requester_phone>
      <requester_billingdata>{doc.name}</requester_billingdata>
    </orderInfo>

    <subject>
      <country>USA</country>
      <name_first>{name_first}</name_first>
      <name_middle>{name_middle}</name_middle>
      <name_last>{name_last}</name_last>
      <dob>{dob}</dob>
      <email>{emp_email}</email>
      <portalfromapplicant>Y</portalfromapplicant>
    </subject>

    <subOrder type="National Alias Criminal"/>

    <postBackInfo>
      <guID>{doc.name}</guID>
      <URL>{settings.postback_url}</URL>
      <postback_types>{postback_types}</postback_types>
    </postBackInfo>

  </placeOrder>

</Accio_Order>
"""

    # Call Sapphire / AccioData API
    try:
        response = requests.post(
            settings.endpoint_url,
            data=xml_payload.encode("utf-8"),
            headers={"Content-Type": "text/xml; charset=utf-8"},
            timeout=30
        )

        doc.raw_place_response = response.text
        frappe.log_error(response.text, "Sapphire Place Order Response")

        # Parse Accio Order ID from response
        try:
            root = ET.fromstring(response.text)

            # Sapphire returns <order orderID="..."> on place order
            order = root.find(".//order")
            if order is not None:
                doc.accio_order_id = order.attrib.get("orderID")
                doc.status = "Order Placed"
                frappe.log_error(
                    f"Order Placed Successfully. Accio Order ID: {doc.accio_order_id}",
                    "BGV Place Order Success"
                )
            else:
                doc.status = "Order Failed"
                frappe.log_error(
                    f"Order node missing in response: {response.text}",
                    "BGV Place Order Failed"
                )

        except ET.ParseError as e:
            doc.status = "Parse Error"
            frappe.log_error(str(e), "BGV Place Order Parse Error")

    except requests.exceptions.RequestException as e:
        doc.raw_place_response = str(e)
        doc.status = "Connection Error"
        frappe.log_error(str(e), "BGV Place Order Connection Error")

    doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {
        "message": "BGV Order submitted",
        "bgv_order": doc.name,
        "accio_order_id": doc.accio_order_id,
        "status": doc.status,
        "sapphire_response": doc.raw_place_response
    }


@frappe.whitelist(allow_guest=True)
def receive_webhook():

    raw_data = frappe.request.data

    if not raw_data:
        frappe.log_error("No payload received", "Webhook Error")
        return {"status": "error", "message": "No payload received"}

    payload = raw_data.decode("utf-8")

    # Log exactly what Sapphire sends
    frappe.log_error(payload, "Sapphire Postback Raw Payload")

    # Parse webhook XML
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as e:
        frappe.log_error(str(e), "Webhook XML Parse Error")
        return {"status": "error", "message": f"XML parse error: {str(e)}"}

    # Sapphire sends <completeOrder remote_number="...">
    order_node = root.find(".//completeOrder")

    if order_node is None:
        frappe.log_error(
            f"completeOrder node missing. Full XML: {payload}",
            "Webhook Error"
        )
        return {
            "status": "error",
            "message": "completeOrder node missing in payload"
        }

    # Get order ID from remote_number
    order_id = order_node.attrib.get("remote_number")
    frappe.log_error(
        f"Received remote_number (orderID): {order_id}",
        "Webhook Debug"
    )

    if not order_id:
        frappe.log_error(
            "remote_number missing in completeOrder node",
            "Webhook Error"
        )
        return {
            "status": "error",
            "message": "remote_number missing in completeOrder node"
        }

    # -------------------------------------------------------
    # Detect Postback Type — IPC / IPV / OCR
    # -------------------------------------------------------
    order_state_node = root.find(".//order_state")
    order_state = order_state_node.text.strip() if order_state_node is not None else ""

    frappe.log_error(
        f"Order State received: {order_state}",
        "Webhook Postback Type Debug"
    )

    # Detect postback type based on order_state
    if "candidate" in order_state.lower():
        postback_type = "IPC"  # Waiting for applicant
    elif "inprogress" in order_state.lower() and "candidate" not in order_state.lower():
        postback_type = "IPV"  # Order went active / in progress vendor
    elif "complete" in order_state.lower():
        postback_type = "OCR"  # Order fully complete
    else:
        postback_type = "UNKNOWN"

    frappe.log_error(
        f"Detected Postback Type: {postback_type} for orderID: {order_id}",
        "Webhook Postback Type"
    )

    # -------------------------------------------------------
    # Find BGV Order by Accio Order ID
    # -------------------------------------------------------
    bgv_order_name = frappe.db.get_value(
        "BGV Order",
        {"accio_order_id": order_id},
        "name"
    )

    frappe.log_error(
        f"BGV Order found: {bgv_order_name} for orderID: {order_id}",
        "Webhook Debug"
    )

    if not bgv_order_name:
        frappe.log_error(
            f"No BGV Order found for orderID: {order_id}",
            "Webhook Error"
        )
        return {
            "status": "error",
            "message": f"BGV Order not found for orderID: {order_id}"
        }

    doc = frappe.get_doc("BGV Order", bgv_order_name)

    # Get BGV Settings
    settings = frappe.get_single("BGV Settings")

    # -------------------------------------------------------
    # Handle IPC — Waiting for Applicant
    # -------------------------------------------------------
    if postback_type == "IPC":

        frappe.log_error(
            f"IPC Postback — Waiting for Applicant. OrderID: {order_id}",
            "Webhook IPC"
        )

        # Save applicant portal URL
        portal_url_node = root.find(".//applicantPortalURL")
        if portal_url_node is not None and portal_url_node.text:
            doc.applicant_portal_url = portal_url_node.text.strip()
            frappe.log_error(
                f"Applicant Portal URL: {doc.applicant_portal_url}",
                "Webhook IPC Portal URL"
            )

        # Save raw postback payload
        doc.raw_result_response = payload

        doc.status = "Waiting for Applicant"
        doc.trigger_count = int(doc.trigger_count or 0) + 1
        doc.save(ignore_permissions=True)
        frappe.db.commit()

        frappe.log_error(
            f"IPC processed. Status: Waiting for Applicant. trigger_count: {doc.trigger_count}",
            "Webhook IPC Success"
        )

        return {
            "status": "success",
            "postback_type": "IPC",
            "order_id": order_id,
            "bgv_order": doc.name,
            "trigger_count": doc.trigger_count
        }

    # -------------------------------------------------------
    # Handle IPV — In Progress Vendor (Order went Active)
    # -------------------------------------------------------
    elif postback_type == "IPV":

        frappe.log_error(
            f"IPV Postback — Order In Progress. OrderID: {order_id}",
            "Webhook IPV"
        )

        # Save raw postback payload
        doc.raw_result_response = payload

        doc.status = "In Progress"
        doc.trigger_count = int(doc.trigger_count or 0) + 1
        doc.save(ignore_permissions=True)
        frappe.db.commit()

        frappe.log_error(
            f"IPV processed. Status: In Progress. trigger_count: {doc.trigger_count}",
            "Webhook IPV Success"
        )

        return {
            "status": "success",
            "postback_type": "IPV",
            "order_id": order_id,
            "bgv_order": doc.name,
            "trigger_count": doc.trigger_count
        }

    # -------------------------------------------------------
    # Handle OCR — Order Complete, Fetch Full Results
    # -------------------------------------------------------
    elif postback_type == "OCR":

        frappe.log_error(
            f"OCR Postback — Order Complete. OrderID: {order_id}",
            "Webhook OCR"
        )

        # Save report URLs from postback
        report_html = root.find(".//reportURL/HTML")
        report_pdf_color = root.find(".//reportURL/PDF_Color")
        report_pdf_bw = root.find(".//reportURL/PDF_BW")

        if report_pdf_color is not None and report_pdf_color.text:
            doc.bgv_document_pdf_link = report_pdf_color.text.strip()
            frappe.log_error(
                f"PDF Report URL saved: {doc.bgv_document_pdf_link}",
                "Webhook OCR Report URL"
            )
        elif report_html is not None and report_html.text:
            doc.bgv_document_pdf_link = report_html.text.strip()

        # Call getOrderResults to get full result XML
        xml_payload = f"""<?xml version="1.0" encoding="UTF-8"?>
<Accio_Order>

  <login>
    <account>{settings.account}</account>
    <username>{settings.username}</username>
    <password>{settings.get_password("password")}</password>
  </login>

  <mode>{settings.mode}</mode>

  <getOrderResults orderID="{order_id}" />

</Accio_Order>
"""

        try:
            response = requests.post(
                settings.endpoint_url,
                data=xml_payload.encode("utf-8"),
                headers={"Content-Type": "text/xml; charset=utf-8"},
                timeout=30
            )

            doc.raw_result_response = response.text
            frappe.log_error(
                response.text,
                "Sapphire getOrderResults Response"
            )

        except requests.exceptions.RequestException as e:
            doc.raw_result_response = str(e)
            frappe.log_error(str(e), "Sapphire getOrderResults API Error")

        doc.status = "Completed"
        doc.trigger_count = int(doc.trigger_count or 0) + 1
        doc.save(ignore_permissions=True)
        frappe.db.commit()

        frappe.log_error(
            f"OCR processed. Status: Completed. trigger_count: {doc.trigger_count}",
            "Webhook OCR Success"
        )

        return {
            "status": "success",
            "postback_type": "OCR",
            "order_id": order_id,
            "bgv_order": doc.name,
            "trigger_count": doc.trigger_count
        }

    # -------------------------------------------------------
    # Handle Unknown Postback Type
    # -------------------------------------------------------
    else:

        frappe.log_error(
            f"Unknown postback type. order_state: {order_state}. OrderID: {order_id}",
            "Webhook Unknown Type"
        )

        # Save raw payload and increment trigger count
        doc.raw_result_response = payload
        doc.trigger_count = int(doc.trigger_count or 0) + 1
        doc.save(ignore_permissions=True)
        frappe.db.commit()

        return {
            "status": "success",
            "postback_type": "UNKNOWN",
            "order_id": order_id,
            "bgv_order": doc.name,
            "trigger_count": doc.trigger_count
        }