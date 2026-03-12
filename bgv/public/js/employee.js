frappe.ui.form.on("Employee", {
    refresh(frm) {

        frm.add_custom_button("Place BGV Order", function() {
            frappe.call({
                method: "bgv.api.place_bgv_order",
                args: {
                    employee: frm.doc.name
                },
                freeze: true,
                freeze_message: __('Creating BGV Order...'),
                callback: function(r) {
                    frappe.msgprint(r.message);
                }
            });
        }, __('Actions'));

    }
    });