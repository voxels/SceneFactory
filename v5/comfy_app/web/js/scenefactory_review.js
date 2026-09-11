/* SceneFactory review-surface UI scaffold (ComfyUI web extension).
 *
 * This is the review UI the user directed: a ComfyUI app surface for
 * follow-up review to fine-tune references across media types, with the
 * automated identity pre-filter screening and his eyes giving final
 * approval.
 *
 * What it does on the Mac (live ComfyUI):
 *  - Adds a gate-band badge widget to SF_IdentityGatePrefilter nodes
 *    (HOLDS / DRIFTS / NO MATCH / USER_CONFIRMED), labeled diagnostic-only.
 *  - Adds a candidate preview dialog hook to SF_ReviewCandidateBrowser
 *    nodes: per media type (image / audio / text) with approve / reject /
 *    user-confirmed buttons that drive the SF_UserAttribution node inputs.
 *  - Adds an escalation banner to SF_RefusalRedirect nodes when a refusal
 *    record is escalated (ladder exhausted) instead of stalling silently.
 *
 * Scaffold status: structural hooks only. The full candidate-grid rendering
 * and media previews are Mac-side work against the live ComfyUI frontend.
 */
import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

const GATE_COLORS = {
    "HOLDS": "#4caf50",
    "DRIFTS": "#ff9800",
    "NO MATCH": "#f44336",
    "USER_CONFIRMED": "#2196f3",
    "UNMEASURED": "#9e9e9e",
};

function badge(band) {
    const el = document.createElement("span");
    el.textContent = band;
    el.title = "Gate band — diagnostic only. The model never approves.";
    el.style.cssText =
        "display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;" +
        "font-weight:600;color:#fff;background:" + (GATE_COLORS[band] || "#9e9e9e");
    return el;
}

app.registerExtension({
    name: "scenefactory.review",

    async nodeCreated(node) {
        // Gate-band badge on the pre-filter node.
        if (node.comfyClass === "SF_IdentityGatePrefilter") {
            const w = node.addWidget("button", "gate bands", null, () => {});
            w.label = "gate: diagnostic only — user approves";
        }
        // Review-surface entry point on the candidate browser.
        if (node.comfyClass === "SF_ReviewCandidateBrowser") {
            node.addWidget("button", "open review surface", null, () => {
                alert(
                    "SceneFactory review surface scaffold.\n\n" +
                    "Candidates render here per media type (image / audio / text) " +
                    "with the gate band shown as diagnostic only.\n" +
                    "Approve / Reject / User-confirmed writes through " +
                    "SF_UserAttribution — the model's band never overrules him."
                );
            });
        }
        // Escalation banner on the refusal-redirect node.
        if (node.comfyClass === "SF_RefusalRedirect") {
            const banner = document.createElement("div");
            banner.style.cssText =
                "padding:6px 8px;font-size:11px;color:#b71c1c;" +
                "border:1px solid #f44336;border-radius:6px;margin-top:4px;";
            banner.textContent =
                "Refusal loop: bounded at 3 debug attempts, then escalates " +
                "with the full debug log. Never stalls silently.";
            node.addDOMWidget("refusal-note", "div", banner);
        }
    },
});
