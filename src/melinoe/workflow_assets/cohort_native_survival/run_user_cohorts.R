options(stringsAsFactors = FALSE)

if (!requireNamespace("survival", quietly = TRUE)) {
  stop("The recommended R package 'survival' is required")
}

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 2L) {
  stop("Usage: Rscript run_user_cohorts.R INPUT.csv OUTPUT_DIRECTORY")
}
input_path <- normalizePath(args[[1L]], mustWork = TRUE)
output_dir <- args[[2L]]
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

data <- read.csv(input_path, check.names = FALSE)
required <- c("cohort", "patient_id", "time", "event", "expression")
missing <- setdiff(required, names(data))
if (length(missing)) stop("Missing required columns: ", paste(missing, collapse = ", "))
data <- data[, required]
data$cohort <- trimws(as.character(data$cohort))
data$patient_id <- trimws(as.character(data$patient_id))
data$time <- suppressWarnings(as.numeric(data$time))
data$event <- suppressWarnings(as.integer(data$event))
data$expression <- suppressWarnings(as.numeric(data$expression))

if (any(!nzchar(data$cohort)) || any(!nzchar(data$patient_id))) {
  stop("Cohort and patient identifiers must be non-empty")
}
if (any(!is.finite(data$time)) || any(data$time <= 0)) {
  stop("Every follow-up time must be finite and positive")
}
if (any(!data$event %in% c(0L, 1L))) {
  stop("Event must be encoded as 0 or 1")
}
if (any(!is.finite(data$expression))) {
  stop("Expression must be finite")
}
keys <- paste(data$cohort, data$patient_id, sep = "\r")
if (anyDuplicated(keys)) {
  stop("Each patient may occur only once within a cohort")
}

cohorts <- split(data, data$cohort)
if (length(cohorts) < 2L) stop("At least two independent cohorts are required")

standardize <- function(x) {
  s <- stats::sd(x)
  if (!is.finite(s) || s == 0) stop("Expression is constant within a cohort")
  (x - mean(x)) / s
}

cohorts <- lapply(cohorts, function(x) {
  if (nrow(x) < 20L || sum(x$event) < 10L) {
    stop(unique(x$cohort), " has fewer than 20 patients or 10 events")
  }
  x$expression_z <- standardize(x$expression)
  x
})

fit_one_cohort <- function(x) {
  fit <- survival::coxph(
    survival::Surv(time, event) ~ expression_z,
    data = x,
    ties = "efron",
    x = TRUE
  )
  sm <- summary(fit)
  ph <- survival::cox.zph(fit)$table
  data.frame(
    cohort = x$cohort[[1L]],
    n = nrow(x),
    events = sum(x$event),
    log_hr = unname(stats::coef(fit)[[1L]]),
    se = sqrt(stats::vcov(fit)[1L, 1L]),
    hr_per_sd = unname(exp(stats::coef(fit)[[1L]])),
    ci_low = unname(exp(stats::confint(fit)[1L])),
    ci_high = unname(exp(stats::confint(fit)[2L])),
    p_value = sm$coefficients[1L, "Pr(>|z|)"],
    c_index = unname(sm$concordance[[1L]]),
    ph_test_p = ph["expression_z", "p"],
    stringsAsFactors = FALSE
  )
}

random_effects_reml <- function(yi, sei) {
  vi <- sei^2
  objective <- function(tau2) {
    w <- 1 / (vi + tau2)
    mu <- sum(w * yi) / sum(w)
    0.5 * (sum(log(vi + tau2)) + log(sum(w)) + sum(w * (yi - mu)^2))
  }
  upper <- max(1, 10 * stats::var(yi), max(vi) * 20)
  tau2 <- optimize(objective, interval = c(0, upper), tol = 1e-12)$minimum
  w <- 1 / (vi + tau2)
  mu <- sum(w * yi) / sum(w)
  q_re <- sum(w * (yi - mu)^2)
  hk_scale <- max(1, q_re / (length(yi) - 1L))
  se_hk <- sqrt(hk_scale / sum(w))
  crit <- stats::qt(0.975, df = length(yi) - 1L)
  p <- 2 * stats::pt(-abs(mu / se_hk), df = length(yi) - 1L)
  w_fixed <- 1 / vi
  typical_variance <- (length(yi) - 1L) * sum(w_fixed) /
    (sum(w_fixed)^2 - sum(w_fixed^2))
  i2 <- 100 * tau2 / (tau2 + typical_variance)
  pred_crit <- stats::qt(0.975, df = max(1L, length(yi) - 2L))
  pred_se <- sqrt(tau2 + se_hk^2)
  c(
    k = length(yi), log_hr = mu, se_hk = se_hk,
    hr = exp(mu), ci_low = exp(mu - crit * se_hk),
    ci_high = exp(mu + crit * se_hk), p_value = p,
    tau2 = tau2, i2_percent = i2,
    prediction_low = exp(mu - pred_crit * pred_se),
    prediction_high = exp(mu + pred_crit * pred_se)
  )
}

flow <- do.call(rbind, lapply(cohorts, function(x) {
  data.frame(
    cohort = x$cohort[[1L]], patients = nrow(x), events = sum(x$event),
    censored = sum(x$event == 0L), stringsAsFactors = FALSE
  )
}))
cox_results <- do.call(rbind, lapply(cohorts, fit_one_cohort))
meta <- random_effects_reml(cox_results$log_hr, cox_results$se)
meta_table <- as.data.frame(as.list(meta), stringsAsFactors = FALSE)

write.csv(flow, file.path(output_dir, "cohort_flow.csv"), row.names = FALSE)
write.csv(cox_results, file.path(output_dir, "cohort_cox_results.csv"), row.names = FALSE)
write.csv(meta_table, file.path(output_dir, "random_effects_meta.csv"), row.names = FALSE)

if (nrow(cox_results) >= 3L) {
  loco <- do.call(rbind, lapply(seq_len(nrow(cox_results)), function(i) {
    estimate <- random_effects_reml(cox_results$log_hr[-i], cox_results$se[-i])
    data.frame(omitted = cox_results$cohort[[i]], as.list(estimate), check.names = FALSE)
  }))
  write.csv(loco, file.path(output_dir, "leave_one_cohort_out.csv"), row.names = FALSE)
}

png(file.path(output_dir, "forest_survival_meta.png"), width = 1800, height = 1100, res = 180)
par(mar = c(5, 10, 4, 2))
y <- rev(seq_len(nrow(cox_results))) + 1
xlim <- range(c(cox_results$ci_low, meta[c("ci_low", "ci_high")]), finite = TRUE)
plot(
  cox_results$hr_per_sd, y, log = "x", xlim = xlim,
  ylim = c(0.5, max(y) + 0.8), yaxt = "n",
  xlab = "Hazard ratio per within-cohort SD", ylab = "", pch = 19,
  main = "Cohort-native survival synthesis"
)
segments(cox_results$ci_low, y, cox_results$ci_high, y, lwd = 2)
axis(2, at = y, labels = cox_results$cohort, las = 1)
abline(v = 1, lty = 2, col = "grey50")
points(meta["hr"], 0.9, pch = 18, cex = 1.7, col = "#005B70")
segments(meta["ci_low"], 0.9, meta["ci_high"], 0.9, lwd = 3, col = "#005B70")
axis(2, at = 0.9, labels = "REML + Hartung-Knapp", las = 1, tick = FALSE)
dev.off()

writeLines(
  c(
    "Melinoe cohort-native survival synthesis",
    paste("Generated:", format(Sys.time(), tz = "UTC", usetz = TRUE)),
    paste("Input file:", basename(input_path)),
    paste("Cohorts:", nrow(flow)),
    paste("Patients:", sum(flow$patients)),
    paste("Events:", sum(flow$events)),
    paste("Pooled HR:", signif(meta["hr"], 5)),
    "No cross-platform harmonization was performed."
  ),
  file.path(output_dir, "run_manifest.txt")
)
