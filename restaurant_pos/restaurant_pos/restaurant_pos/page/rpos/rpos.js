// Page entry point — loaded by Frappe when /rpos is navigated to.
frappe.pages["rpos"].on_page_load = function (wrapper) {
    // Surface any JS errors visibly so we can diagnose
    try {
        if (typeof rpos === "undefined" || typeof rpos.App === "undefined") {
            $(wrapper).html(
                '<div style="padding:2rem;font-family:monospace;color:red;">' +
                '<h3>RPOS: rpos.App class not found</h3>' +
                '<p>rpos_app.js did not load or failed to execute.</p>' +
                '<p>typeof rpos = ' + (typeof rpos) + '</p>' +
                '</div>'
            );
            return;
        }
        frappe.pages["rpos"].app = new rpos.App(wrapper);
    } catch (e) {
        $(wrapper).html(
            '<div style="padding:2rem;font-family:monospace;color:red;">' +
            '<h3>RPOS startup error</h3>' +
            '<pre>' + (e.stack || e.message || String(e)) + '</pre>' +
            '</div>'
        );
        console.error("RPOS startup error:", e);
    }
};

frappe.pages["rpos"].on_page_show = function () {
    if (frappe.pages["rpos"].app) frappe.pages["rpos"].app.onShow();
};
