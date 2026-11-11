/*
 * Reports dashboard charts (Chart.js, stored locally).
 * Every chart is single-series: one colour (series-1), no legend (the title names it),
 * thin bars with 4px rounded ends, 2px lines, recessive grid, hover tooltip on every mark,
 * and a data table under each chart for anyone who can't read the chart.
 */
(function () {
  var dataEl = document.getElementById("report-data");
  if (!dataEl || typeof Chart === "undefined") return;
  var stats = JSON.parse(dataEl.textContent);
  if (!stats) return;

  var css = getComputedStyle(document.querySelector(".viz-root"));
  var color = {
    series: css.getPropertyValue("--series-1").trim(),
    hover: css.getPropertyValue("--series-1-hover").trim(),
    grid: css.getPropertyValue("--grid").trim(),
    axis: css.getPropertyValue("--axis-text").trim(),
  };

  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  Chart.defaults.font.size = 12;
  Chart.defaults.color = color.axis;

  var fmt = new Intl.NumberFormat();

  function baseOptions(opts) {
    var valueAxis = opts.horizontal ? "x" : "y";
    var categoryAxis = opts.horizontal ? "y" : "x";
    var scales = {};
    scales[valueAxis] = {
      beginAtZero: true,
      max: opts.max,
      grid: { color: color.grid, drawTicks: false },
      border: { display: false },
      ticks: {
        padding: 6,
        precision: 0,
        callback: function (v) { return fmt.format(v) + (opts.unit || ""); },
      },
    };
    scales[categoryAxis] = { grid: { display: false }, border: { color: color.grid }, ticks: { padding: 4 } };
    return {
      responsive: true,
      maintainAspectRatio: false,
      indexAxis: opts.horizontal ? "y" : "x",
      animation: false,
      interaction: { mode: opts.line ? "index" : "nearest", intersect: !opts.line, axis: opts.horizontal ? "y" : "x" },
      plugins: {
        legend: { display: false },
        tooltip: {
          displayColors: false,
          callbacks: {
            label: function (ctx) {
              var v = opts.horizontal ? ctx.parsed.x : ctx.parsed.y;
              var extra = opts.detail ? opts.detail(ctx.dataIndex) : "";
              return fmt.format(v) + (opts.unit || "") + (extra ? " · " + extra : "");
            },
          },
        },
      },
      scales: scales,
    };
  }

  function bar(id, labels, values, opts) {
    var el = document.getElementById(id);
    if (!el || !labels.length) return;
    opts = opts || {};
    new Chart(el, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [{
          data: values,
          backgroundColor: color.series,
          hoverBackgroundColor: color.hover,
          borderRadius: 4,
          borderSkipped: "start", // round the data end only; the baseline end stays square
          maxBarThickness: 28,
          categoryPercentage: 0.7,
        }],
      },
      options: baseOptions(opts),
    });
  }

  function line(id, labels, values, opts) {
    var el = document.getElementById(id);
    if (!el || !labels.length) return;
    opts = Object.assign({ line: true }, opts || {});
    new Chart(el, {
      type: "line",
      data: {
        labels: labels,
        datasets: [{
          data: values,
          borderColor: color.series,
          backgroundColor: color.series,
          borderWidth: 2,
          pointRadius: 4,          // 8px marker
          pointHoverRadius: 6,
          pointBorderColor: "#fff", // surface ring so markers stay distinct
          pointBorderWidth: 2,
          tension: 0,
          spanGaps: true,
        }],
      },
      options: baseOptions(opts),
    });
  }

  var projects = stats.by_project.filter(function (p) { return p.positivity !== null; });
  bar("chart-positivity", projects.map(function (p) { return p.project__code; }),
    projects.map(function (p) { return p.positivity; }),
    { horizontal: true, max: 100, unit: "%",
      detail: function (i) { return projects[i].positive + " of " + (projects[i].positive + projects[i].negative) + " slides"; } });

  line("chart-monthly-positivity", stats.monthly.map(function (m) { return m.label; }),
    stats.monthly.map(function (m) { return m.positivity; }),
    { max: 100, unit: "%", detail: function (i) { return stats.monthly[i].positive + " of " + stats.monthly[i].total + " slides"; } });

  bar("chart-monthly-count", stats.monthly.map(function (m) { return m.label; }),
    stats.monthly.map(function (m) { return m.total; }), { unit: " slides" });

  bar("chart-species", stats.species.map(function (s) { return s.label; }),
    stats.species.map(function (s) { return s.count; }), { horizontal: true, unit: " slides" });

  bar("chart-density", stats.density.map(function (b) { return b.label; }),
    stats.density.map(function (b) { return b.count; }), { unit: " slides" });

  var doubled = stats.by_project.filter(function (p) { return p.discordance_rate !== null; });
  bar("chart-discordance", doubled.map(function (p) { return p.project__code; }),
    doubled.map(function (p) { return p.discordance_rate; }),
    { horizontal: true, unit: "%",
      detail: function (i) { return doubled[i].discordant + " of " + doubled[i].double_read + " double-read slides"; } });
})();
