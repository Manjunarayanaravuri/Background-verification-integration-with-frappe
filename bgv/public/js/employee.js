frappe.ui.form.on("Employee", {
    refresh(frm) {

        frm.add_custom_button("Place BGV Order", function() {

            // Fetch all active BGV Check Types
            frappe.call({
                method: "frappe.client.get_list",
                args: {
                    doctype: "BGV Check Type",
                    filters: { is_active: 1 },
                    fields: ["name", "check_type_name", "sapphire_code"],
                    limit_page_length: 100
                },
                callback: function(r) {
                    if (!r.message || r.message.length === 0) {
                        frappe.msgprint("No BGV Check Types found. Please add them first.");
                        return;
                    }

                    let check_types = r.message;

                    // Build checkbox HTML for dialog
                    let checkbox_html = `
                        <div style="max-height: 400px; overflow-y: auto; padding: 10px;">
                            <div style="margin-bottom: 10px;">
                                <button class="btn btn-xs btn-default" id="select_all_checks">
                                    Select All
                                </button>
                                <button class="btn btn-xs btn-default" style="margin-left:5px;" id="clear_all_checks">
                                    Clear All
                                </button>
                            </div>
                            <table class="table table-bordered table-sm">
                                <thead>
                                    <tr>
                                        <th width="10%">Select</th>
                                        <th>Check Type</th>
                                        <th>Sapphire Code</th>
                                    </tr>
                                </thead>
                                <tbody>
                    `;

                    check_types.forEach(function(ct) {
                        checkbox_html += `
                            <tr>
                                <td style="text-align:center;">
                                    <input 
                                        type="checkbox" 
                                        class="bgv-check-checkbox"
                                        data-sapphire-code="${ct.sapphire_code}"
                                        data-check-name="${ct.check_type_name}"
                                        style="width:16px; height:16px;"
                                    />
                                </td>
                                <td>${ct.check_type_name}</td>
                                <td><code>${ct.sapphire_code}</code></td>
                            </tr>
                        `;
                    });

                    checkbox_html += `
                                </tbody>
                            </table>
                        </div>
                    `;

                    // Show dialog
                    let d = new frappe.ui.Dialog({
                        title: "Place BGV Order — Select Checks",
                        fields: [
                            {
                                fieldtype: "HTML",
                                fieldname: "check_types_html",
                                options: checkbox_html
                            }
                        ],
                        primary_action_label: "Place Order",
                        primary_action: function() {

                            // Get selected checks
                            let selected = [];
                            d.$wrapper.find(".bgv-check-checkbox:checked").each(function() {
                                selected.push({
                                    sapphire_code: $(this).data("sapphire-code"),
                                    check_name: $(this).data("check-name")
                                });
                            });

                            if (selected.length === 0) {
                                frappe.msgprint({
                                    title: "Validation",
                                    message: "Please select at least one BGV Check Type.",
                                    indicator: "red"
                                });
                                return;
                            }

                            d.hide();

                            // Show selected checks summary
                            let selected_names = selected.map(s => s.check_name).join(", ");
                            frappe.show_alert({
                                message: `Placing BGV Order with ${selected.length} check(s): ${selected_names}`,
                                indicator: "blue"
                            });

                            // Call API
                            frappe.call({
                                method: "bgv.api.place_bgv_order",
                                args: {
                                    employee: frm.doc.name,
                                    selected_checks: selected
                                },
                                freeze: true,
                                freeze_message: __("Creating BGV Order..."),
                                callback: function(r) {
                                    if (r.message) {
                                        frappe.msgprint({
                                            title: "BGV Order Placed",
                                            message: `
                                                <b>BGV Order:</b> ${r.message.bgv_order}<br>
                                                <b>Accio Order ID:</b> ${r.message.accio_order_id}<br>
                                                <b>Status:</b> ${r.message.status}<br>
                                                <b>Checks Ordered:</b> ${selected_names}
                                            `,
                                            indicator: "green"
                                        });
                                        frm.reload_doc();
                                    }
                                }
                            });
                        }
                    });

                    d.show();

                    // Select All button
                    d.$wrapper.find("#select_all_checks").on("click", function() {
                        d.$wrapper.find(".bgv-check-checkbox").prop("checked", true);
                    });

                    // Clear All button
                    d.$wrapper.find("#clear_all_checks").on("click", function() {
                        d.$wrapper.find(".bgv-check-checkbox").prop("checked", false);
                    });
                }
            });

        }, __("Actions"));
    }
});