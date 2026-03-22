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

  if (typeof courseInformation === "undefined" || !Array.isArray(courseInformation)) {
    alert("SheetHappens: Not on the Learning Suite schedule page.\nNavigate to the Schedule tab and try again.");
    return;
  }

  var total = courseInformation.reduce(function (sum, c) {
    return sum + (c.assignments ? c.assignments.length : 0);
  }, 0);

  if (total === 0) {
    alert("SheetHappens: No assignments found on this page.");
    return;
  }

  fetch(BACKEND_URL + "/sync/learning-suite", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ courses: courseInformation, page_url: window.location.href }),
  })
    .then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
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
      alert("SheetHappens sync failed: " + e + "\nCheck that your backend is running.");
    });
})();
