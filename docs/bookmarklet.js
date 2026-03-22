// SheetHappens — Learning Suite Bookmarklet
//
// SETUP:
//   1. Replace BACKEND_URL with your Railway deployment URL (no trailing slash)
//   2. Minify this file (e.g. paste into https://www.toptal.com/developers/javascript-minifier)
//   3. Prepend "javascript:" to the minified output
//   4. Save as a browser bookmark — name it something like "Sync LS → Sheets"
//
// USAGE:
//   Navigate to https://learningsuite.byu.edu/.{id}/student/top/schedule
//   Click the bookmark — a popup will confirm how many assignments were synced.

(function () {
  var BACKEND_URL = "https://ohsheet-production.up.railway.app";

  if (!window.location.href.includes("learningsuite.byu.edu")) {
    alert("SheetHappens: Not on a Learning Suite page.");
    return;
  }

  // courseInformation is inside a require() closure so it's not on window.
  // Fetch the page HTML (same-origin, no CORS) and extract it directly.
  function extractJSON(html, varName) {
    var marker = "var " + varName + " = ";
    var idx = html.indexOf(marker);
    if (idx === -1) return null;
    idx += marker.length;
    while (idx < html.length && html[idx] !== "[" && html[idx] !== "{") idx++;
    var depth = 0, inStr = false, escape = false, start = idx;
    for (; idx < html.length; idx++) {
      var c = html[idx];
      if (escape) { escape = false; continue; }
      if (c === "\\" && inStr) { escape = true; continue; }
      if (c === '"' && !inStr) { inStr = true; continue; }
      if (c === '"' && inStr) { inStr = false; continue; }
      if (inStr) continue;
      if (c === "[" || c === "{") depth++;
      else if (c === "]" || c === "}") { if (--depth === 0) return html.substring(start, idx + 1); }
    }
    return null;
  }

  alert("SheetHappens: Syncing... this will take a few seconds.");

  var today = new Date();
  today.setHours(0, 0, 0, 0);

  fetch(window.location.href)
    .then(function (r) { return r.text(); })
    .then(function (html) {
      var raw = extractJSON(html, "courseInformation");
      if (!raw) {
        alert("SheetHappens: Could not find courseInformation on this page.\nMake sure you are on the Schedule tab.");
        return;
      }
      var courses = JSON.parse(raw);
      // Filter each course's assignments to only upcoming/today ones
      courses = courses.map(function (c) {
        return Object.assign({}, c, {
          assignments: (c.assignments || []).filter(function (a) {
            if (!a.dueDate) return false;
            var due = new Date(a.dueDate.replace(" ", "T"));
            return due >= today;
          })
        });
      });
      var total = courses.reduce(function (sum, c) {
        return sum + c.assignments.length;
      }, 0);
      if (total === 0) {
        alert("SheetHappens: No upcoming assignments found.");
        return;
      }
      return fetch(BACKEND_URL + "/sync/learning-suite", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ courses: courses, page_url: window.location.href }),
      });
    })
    .then(function (r) {
      if (!r || !r.ok) throw new Error("HTTP " + (r ? r.status : "no response"));
      return r.json();
    })
    .then(function (d) {
      alert(
        "SheetHappens sync complete!\n" +
        "  Synced:   " + d.synced + "\n" +
        "  Skipped:  " + d.skipped + " (already in sheet)\n" +
        "  Failures: " + d.failures
      );
    })
    .catch(function (e) {
      alert("SheetHappens sync failed: " + e);
    });
})();
