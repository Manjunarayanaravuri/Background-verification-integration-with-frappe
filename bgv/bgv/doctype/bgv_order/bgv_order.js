frappe.ui.form.on("BGV Order", {
    refresh(frm) {

        if (!frm.is_new()) {
            frm.add_custom_button("Fetch Results", function() {
                frappe.call({
                    method: "bgv.api.fetch_bgv_results",
                    args: {
                        bgv_order: frm.doc.name
                    },
                    callback: function(r) {
                        frappe.msgprint(r.message);
                        frm.reload_doc();
                    }
                });
            });
        }

    }
});