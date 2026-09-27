options(stringsAsFactors = FALSE, timeout = max(1200, getOption("timeout")))

if (!requireNamespace("survival", quietly = TRUE)) {
  stop("The recommended R package 'survival' is required")
}

set.seed(20260912)
cache_dir <- Sys.getenv(
  "MELINOE_DATA_CACHE",
  unset = file.path("data", "v2", "cache")
)
result_dir <- Sys.getenv(
  "MELINOE_RESULT_DIR",
  unset = file.path("results", "v2")
)
figure_dir <- file.path(result_dir, "figures")
table_dir <- file.path(result_dir, "tables")
dir.create(cache_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(figure_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(table_dir, recursive = TRUE, showWarnings = FALSE)

cbioportal_datahub_revision <- "0cc9138746c08b304f8dac92c31983e0ef44af1d"
cbioportal_base <- paste0(
  "https://media.githubusercontent.com/media/cBioPortal/datahub/",
  cbioportal_datahub_revision, "/"
)
sources <- c(
  data_mrna_seq_v2_rsem.txt = paste0(
    cbioportal_base,
    "public/paad_tcga_pan_can_atlas_2018/data_mrna_seq_v2_rsem.txt"
  ),
  data_clinical_patient.txt = paste0(
    cbioportal_base,
    "public/paad_tcga_pan_can_atlas_2018/data_clinical_patient.txt"
  ),
  data_clinical_sample.txt = paste0(
    cbioportal_base,
    "public/paad_tcga_pan_can_atlas_2018/data_clinical_sample.txt"
  ),
  GSE85916_series_matrix.txt.gz = paste0(
    "https://ftp.ncbi.nlm.nih.gov/geo/series/GSE85nnn/GSE85916/matrix/",
    "GSE85916_series_matrix.txt.gz"
  ),
  GSE57495_series_matrix.txt.gz = paste0(
    "https://ftp.ncbi.nlm.nih.gov/geo/series/GSE57nnn/GSE57495/matrix/",
    "GSE57495_series_matrix.txt.gz"
  ),
  GSE62452_series_matrix.txt.gz = paste0(
    "https://ftp.ncbi.nlm.nih.gov/geo/series/GSE62nnn/GSE62452/matrix/",
    "GSE62452_series_matrix.txt.gz"
  ),
  GSE164665_Cancer_raw_gene_counts.txt.gz = paste0(
    "https://ftp.ncbi.nlm.nih.gov/geo/series/GSE164nnn/GSE164665/suppl/",
    "GSE164665_Cancer_raw_gene_counts.txt.gz"
  ),
  GSE164665_Stroma_raw_gene_counts.txt.gz = paste0(
    "https://ftp.ncbi.nlm.nih.gov/geo/series/GSE164nnn/GSE164665/suppl/",
    "GSE164665_Stroma_raw_gene_counts.txt.gz"
  ),
  cptac_data_mrna_seq_v2_rsem.txt = paste0(
    cbioportal_base,
    "public/paad_cptac_2021/data_mrna_seq_v2_rsem.txt"
  ),
  cptac_data_protein_quantification.txt = paste0(
    cbioportal_base,
    "public/paad_cptac_2021/data_protein_quantification.txt"
  ),
  cptac_data_clinical_patient.txt = paste0(
    cbioportal_base,
    "public/paad_cptac_2021/data_clinical_patient.txt"
  ),
  cptac_data_clinical_sample.txt = paste0(
    cbioportal_base,
    "public/paad_cptac_2021/data_clinical_sample.txt"
  )
)

for (filename in names(sources)) {
  destination <- file.path(cache_dir, filename)
  if (!file.exists(destination)) {
    message("Downloading ", filename)
    download.file(sources[[filename]], destination, mode = "wb")
  }
}

input_paths <- file.path(cache_dir, names(sources))
input_info <- file.info(input_paths)
expected_md5 <- c(
  data_mrna_seq_v2_rsem.txt = "00236ecd40af3963e9749c121b4c75c8",
  data_clinical_patient.txt = "b160e28d5380f438a429e1b6d4d6b0e3",
  data_clinical_sample.txt = "7e6c3490ca86c3a8a717233793f1a5bd",
  GSE85916_series_matrix.txt.gz = "036cf38d34bd818ade105f03e37bb332",
  GSE57495_series_matrix.txt.gz = "edae2ac6094c3a73046b6e74743206d8",
  GSE62452_series_matrix.txt.gz = "e5508574d471e212aa8c9ce3435791f3",
  GSE164665_Cancer_raw_gene_counts.txt.gz = "cc0bdd4d715073fdbef9db612daed2ab",
  GSE164665_Stroma_raw_gene_counts.txt.gz = "754a694fb40bc754da63c234954754d3",
  cptac_data_mrna_seq_v2_rsem.txt = "200873b1bbd31225cc416156185c8e91",
  cptac_data_protein_quantification.txt = "c6e3273b37353e1ec3aead69d8ed9832",
  cptac_data_clinical_patient.txt = "2c003731234d72684175515cc6e383c1",
  cptac_data_clinical_sample.txt = "2580dbf7f989ab3becf7170ce0324d9c"
)
actual_md5 <- unname(tools::md5sum(input_paths))
if (!identical(actual_md5, unname(expected_md5[names(sources)]))) {
  mismatch <- names(sources)[actual_md5 != unname(expected_md5[names(sources)])]
  stop("Input checksum mismatch: ", paste(mismatch, collapse = ", "))
}
write.csv(
  data.frame(
    file = names(sources),
    source_url = unname(sources),
    bytes = input_info$size,
    md5 = actual_md5,
    stringsAsFactors = FALSE
  ),
  file.path(table_dir, "input_manifest.csv"),
  row.names = FALSE
)

read_cbio <- function(path) {
  read.delim(
    path, header = TRUE, sep = "\t", comment.char = "#",
    quote = "", check.names = FALSE,
    na.strings = c("", "NA", "NaN", "[Not Available]")
  )
}

split_fields <- function(line) {
  fields <- strsplit(line, "\t", fixed = TRUE)[[1L]]
  sub('"$', "", sub('^"', "", fields))
}

read_geo_probes <- function(path, probes) {
  con <- gzfile(path, open = "rt")
  on.exit(close(con), add = TRUE)
  metadata <- character()
  header <- NULL
  rows <- list()
  in_table <- FALSE
  finished <- FALSE
  while (!finished) {
    chunk <- readLines(con, n = 1000L, warn = FALSE)
    if (!length(chunk)) break
    for (line in chunk) {
      if (!in_table) {
        if (startsWith(line, "!Series_") || startsWith(line, "!Sample_")) {
          metadata <- c(metadata, line)
        }
        if (identical(line, "!series_matrix_table_begin")) in_table <- TRUE
        next
      }
      if (is.null(header)) {
        header <- split_fields(line)
        next
      }
      if (identical(line, "!series_matrix_table_end")) {
        finished <- TRUE
        break
      }
      first_tab <- regexpr("\t", line, fixed = TRUE)[1L]
      if (first_tab < 1L) next
      id <- sub('"$', "", sub('^"', "", substr(line, 1L, first_tab - 1L)))
      if (id %in% probes) {
        fields <- split_fields(line)
        rows[[id]] <- suppressWarnings(as.numeric(fields[-1L]))
      }
    }
  }
  if (!length(rows)) stop("None of the requested probes were found in ", path)
  values <- do.call(rbind, rows)
  colnames(values) <- header[-1L]
  list(metadata = metadata, values = values)
}

sample_metadata <- function(metadata, prefix, value_prefix = NULL) {
  lines <- metadata[startsWith(metadata, prefix)]
  if (!length(lines)) return(character())
  if (!is.null(value_prefix)) {
    keep <- vapply(lines, function(line) {
      fields <- split_fields(line)[-1L]
      any(startsWith(tolower(fields), tolower(value_prefix)))
    }, logical(1))
    lines <- lines[keep]
  }
  if (!length(lines)) return(character())
  split_fields(lines[1L])[-1L]
}

strip_characteristic <- function(x, label) {
  trimws(sub(paste0("^", label, "\\s*"), "", x, ignore.case = TRUE))
}

standardize <- function(x) {
  x <- as.numeric(x)
  s <- stats::sd(x, na.rm = TRUE)
  if (!is.finite(s) || s == 0) stop("Cannot standardize a constant feature")
  (x - mean(x, na.rm = TRUE)) / s
}

make_cohort <- function(name, platform, sample_id, time, event, expression,
                        age = NA_real_, stage = NA_character_, grade = NA_character_) {
  out <- data.frame(
    cohort = name,
    sample_id = as.character(sample_id),
    patient_id = as.character(sample_id),
    platform = platform,
    specimen_class = "primary_tumor",
    time_months = suppressWarnings(as.numeric(time)),
    event = suppressWarnings(as.integer(event)),
    gprc5a = suppressWarnings(as.numeric(expression)),
    age = suppressWarnings(as.numeric(age)),
    stage = as.character(stage),
    grade = as.character(grade),
    stringsAsFactors = FALSE
  )
  keep <- is.finite(out$time_months) & out$time_months > 0 &
    out$event %in% c(0L, 1L) & is.finite(out$gprc5a)
  out <- out[keep, , drop = FALSE]
  out <- out[!duplicated(out$patient_id), , drop = FALSE]
  out$gprc5a_z <- standardize(out$gprc5a)
  if (nrow(out) < 20L || sum(out$event) < 10L) {
    stop(name, " has insufficient eligible patients/events")
  }
  out
}

# TCGA-PAAD PanCancer Atlas ---------------------------------------------------
tcga_patient <- read_cbio(file.path(cache_dir, "data_clinical_patient.txt"))
tcga_sample_all <- read_cbio(file.path(cache_dir, "data_clinical_sample.txt"))
tcga_expr <- read_cbio(file.path(cache_dir, "data_mrna_seq_v2_rsem.txt"))
tcga_sample <- tcga_sample_all[
  tcga_sample_all$SAMPLE_TYPE == "Primary" &
    tcga_sample_all$TUMOR_TYPE == "Pancreas Adenocarcinoma, Ductal Type",
  , drop = FALSE
]
tcga_clin <- merge(tcga_sample, tcga_patient, by = "PATIENT_ID", all.x = TRUE, sort = FALSE)
tcga_clin$event <- ifelse(
  grepl("^1:", tcga_clin$OS_STATUS), 1L,
  ifelse(grepl("^0:", tcga_clin$OS_STATUS), 0L, NA_integer_)
)
tcga_clin <- tcga_clin[order(tcga_clin$PATIENT_ID, tcga_clin$SAMPLE_ID), ]
tcga_clin <- tcga_clin[!duplicated(tcga_clin$PATIENT_ID), ]
tcga_row <- which(tcga_expr$Hugo_Symbol == "GPRC5A")[1L]
tcga_samples <- intersect(tcga_clin$SAMPLE_ID, names(tcga_expr))
tcga_clin <- tcga_clin[match(tcga_samples, tcga_clin$SAMPLE_ID), ]
tcga <- make_cohort(
  "TCGA_PAAD", "Illumina RNA-seq; cBioPortal RSEM",
  tcga_clin$SAMPLE_ID, tcga_clin$OS_MONTHS, tcga_clin$event,
  log2(as.numeric(tcga_expr[tcga_row, tcga_samples, drop = TRUE]) + 1),
  tcga_clin$AGE, tcga_clin$AJCC_PATHOLOGIC_TUMOR_STAGE,
  tcga_clin$GRADE
)
tcga$patient_id <- tcga_clin$PATIENT_ID[match(tcga$sample_id, tcga_clin$SAMPLE_ID)]

# CPTAC-PAAD ------------------------------------------------------------------
cptac_patient <- read_cbio(file.path(cache_dir, "cptac_data_clinical_patient.txt"))
cptac_sample <- read_cbio(file.path(cache_dir, "cptac_data_clinical_sample.txt"))
cptac_expr <- read_cbio(file.path(cache_dir, "cptac_data_mrna_seq_v2_rsem.txt"))
cptac_protein <- read_cbio(file.path(cache_dir, "cptac_data_protein_quantification.txt"))
cptac_clin <- merge(cptac_sample, cptac_patient, by = "PATIENT_ID", all.x = TRUE, sort = FALSE)
cptac_clin <- cptac_clin[grepl("ductal", cptac_clin$HISTOLOGY_DIAGNOSIS, ignore.case = TRUE), ]
cptac_clin <- cptac_clin[!duplicated(cptac_clin$PATIENT_ID), ]
cptac_row <- which(cptac_expr$Hugo_Symbol == "GPRC5A")[1L]
cptac_samples <- intersect(cptac_clin$SAMPLE_ID, names(cptac_expr))
cptac_clin <- cptac_clin[match(cptac_samples, cptac_clin$SAMPLE_ID), ]
cptac_event <- ifelse(
  tolower(cptac_clin$VITAL_STATUS) == "deceased", 1L,
  ifelse(tolower(cptac_clin$VITAL_STATUS) == "living", 0L, NA_integer_)
)
cptac <- make_cohort(
  "CPTAC_PAAD", "Illumina RNA-seq; CPTAC 2021 cBioPortal",
  cptac_clin$SAMPLE_ID, as.numeric(cptac_clin$FOLLOW_UP_DAYS) / 30.4375,
  cptac_event,
  as.numeric(cptac_expr[cptac_row, cptac_samples, drop = TRUE]),
  cptac_clin$AGE, cptac_clin$TUMOR_STAGE_PATHOLOGICAL, NA_character_
)
cptac$patient_id <- cptac_clin$PATIENT_ID[match(cptac$sample_id, cptac_clin$SAMPLE_ID)]

# GEO survival cohorts --------------------------------------------------------
g859 <- read_geo_probes(
  file.path(cache_dir, "GSE85916_series_matrix.txt.gz"),
  c("11719791_s_at", "11719792_at")
)
g859_id <- sample_metadata(g859$metadata, "!Sample_geo_accession\t")
g859_source <- sample_metadata(g859$metadata, "!Sample_source_name_ch1\t")
g859_time <- strip_characteristic(
  sample_metadata(g859$metadata, "!Sample_characteristics_ch1\t", "os.year:"),
  "os.year:"
)
g859_event <- strip_characteristic(
  sample_metadata(g859$metadata, "!Sample_characteristics_ch1\t", "death:"),
  "death:"
)
if (any(tolower(g859_source) != "pancreatic tumor")) stop("GSE85916 includes a non-tumour sample")
gse85916 <- make_cohort(
  "GSE85916", "GPL13667 Affymetrix Human Genome U219",
  g859_id, as.numeric(g859_time) * 12, g859_event,
  colMeans(g859$values, na.rm = TRUE)
)

g574 <- read_geo_probes(
  file.path(cache_dir, "GSE57495_series_matrix.txt.gz"),
  "merck-NM_003979_at"
)
g574_id <- sample_metadata(g574$metadata, "!Sample_geo_accession\t")
g574_time <- strip_characteristic(
  sample_metadata(g574$metadata, "!Sample_characteristics_ch1\t", "overall survival (month):"),
  "overall survival \\(month\\):"
)
g574_status <- strip_characteristic(
  sample_metadata(g574$metadata, "!Sample_characteristics_ch1\t", "vital.status:"),
  "vital.status:"
)
g574_stage <- strip_characteristic(
  sample_metadata(g574$metadata, "!Sample_characteristics_ch1\t", "stage:"),
  "stage:"
)
gse57495 <- make_cohort(
  "GSE57495", "GPL15048 Rosetta/Merck HuRSTA custom array",
  g574_id, g574_time, ifelse(toupper(g574_status) == "DEAD", 1L, 0L),
  drop(g574$values), stage = g574_stage
)

g624 <- read_geo_probes(
  file.path(cache_dir, "GSE62452_series_matrix.txt.gz"), "7954065"
)
g624_id <- sample_metadata(g624$metadata, "!Sample_geo_accession\t")
g624_title <- sample_metadata(g624$metadata, "!Sample_title\t")
g624_source <- sample_metadata(g624$metadata, "!Sample_source_name_ch1\t")
g624_tissue <- strip_characteristic(
  sample_metadata(g624$metadata, "!Sample_characteristics_ch1\t", "tissue:"), "tissue:"
)
g624_grade <- strip_characteristic(
  sample_metadata(g624$metadata, "!Sample_characteristics_ch1\t", "grading:"), "grading:"
)
g624_stage <- strip_characteristic(
  sample_metadata(g624$metadata, "!Sample_characteristics_ch1\t", "stage:"), "stage:"
)
g624_time <- strip_characteristic(
  sample_metadata(g624$metadata, "!Sample_characteristics_ch1\t", "survival months:"),
  "survival months:"
)
g624_event <- strip_characteristic(
  sample_metadata(g624$metadata, "!Sample_characteristics_ch1\t", "survival status:"),
  "survival status:"
)
g624_all <- data.frame(
  sample_id = g624_id, title = g624_title, source = g624_source,
  tissue = g624_tissue, grade = g624_grade, stage = g624_stage,
  time = suppressWarnings(as.numeric(g624_time)),
  event = suppressWarnings(as.integer(g624_event)),
  gprc5a = drop(g624$values), stringsAsFactors = FALSE
)
g624_tumour <- g624_all[tolower(g624_all$tissue) == "pancreatic tumor", ]
gse62452 <- make_cohort(
  "GSE62452", "GPL6244 Affymetrix Human Gene 1.0 ST",
  g624_tumour$sample_id, g624_tumour$time, g624_tumour$event,
  g624_tumour$gprc5a, stage = g624_tumour$stage, grade = g624_tumour$grade
)

cohorts <- list(
  TCGA_PAAD = tcga,
  CPTAC_PAAD = cptac,
  GSE85916 = gse85916,
  GSE57495 = gse57495,
  GSE62452 = gse62452
)

# This portable table is replayed through Melinoe's generic cohort-native
# engine. It keeps platforms separate and contains one eligible row per patient.
survival_observations <- do.call(rbind, lapply(cohorts, function(x) {
  data.frame(
    cohort = x$cohort,
    patient_id = x$patient_id,
    time = x$time_months,
    event = x$event,
    expression = x$gprc5a,
    stringsAsFactors = FALSE
  )
}))
write.csv(
  survival_observations,
  file.path(table_dir, "survival_observations.csv"),
  row.names = FALSE
)

cohort_flow <- do.call(rbind, lapply(cohorts, function(x) {
  data.frame(
    cohort = x$cohort[1L], platform = x$platform[1L],
    patients = nrow(x), events = sum(x$event), censored = sum(x$event == 0L),
    median_followup_or_death_months = stats::median(x$time_months),
    stringsAsFactors = FALSE
  )
}))
write.csv(cohort_flow, file.path(table_dir, "cohort_flow.csv"), row.names = FALSE)

sample_flow <- data.frame(
  cohort = names(cohorts),
  accession_samples = c(nrow(tcga_sample_all), nrow(cptac_sample), length(g859_id),
                        length(g574_id), length(g624_id)),
  eligible_specimen_type = c(
    nrow(tcga_sample),
    sum(grepl("ductal", cptac_patient$HISTOLOGY_DIAGNOSIS, ignore.case = TRUE)),
    sum(tolower(g859_source) == "pancreatic tumor"),
    length(g574_id),
    sum(tolower(g624_tissue) == "pancreatic tumor")
  ),
  expression_and_survival_complete = vapply(cohorts, nrow, integer(1)),
  excluded_from_survival = c(
    nrow(tcga_sample_all) - nrow(tcga),
    nrow(cptac_sample) - nrow(cptac),
    length(g859_id) - nrow(gse85916),
    length(g574_id) - nrow(gse57495),
    length(g624_id) - nrow(gse62452)
  ),
  exclusion_note = c(
    "non-ductal/unspecified histology, missing/nonpositive OS time, non-explicit status, or no matched expression",
    "adenosquamous histology or missing/nonpositive OS data",
    "one sample with missing OS time",
    "none",
    "adjacent non-tumour specimens or missing OS data"
  ),
  stringsAsFactors = FALSE
)
write.csv(sample_flow, file.path(table_dir, "sample_flow_details.csv"), row.names = FALSE)

# Cohort-specific Cox models --------------------------------------------------
fit_one_cohort <- function(x) {
  fit <- survival::coxph(
    survival::Surv(time_months, event) ~ gprc5a_z,
    data = x, ties = "efron", x = TRUE
  )
  sm <- summary(fit)
  ph <- survival::cox.zph(fit)$table
  data.frame(
    cohort = x$cohort[1L], platform = x$platform[1L],
    n = nrow(x), events = sum(x$event),
    log_hr = unname(stats::coef(fit)[1L]),
    se = sqrt(stats::vcov(fit)[1L, 1L]),
    hr_per_sd = unname(exp(stats::coef(fit)[1L])),
    ci_low = unname(exp(stats::confint(fit)[1L])),
    ci_high = unname(exp(stats::confint(fit)[2L])),
    p_value = sm$coefficients[1L, "Pr(>|z|)"],
    c_index = unname(sm$concordance[1L]),
    ph_test_p = ph["gprc5a_z", "p"],
    stringsAsFactors = FALSE
  )
}

cox_results <- do.call(rbind, lapply(cohorts, fit_one_cohort))
write.csv(cox_results, file.path(table_dir, "cohort_cox_results.csv"), row.names = FALSE)

# Clinical adjustment is a sensitivity analysis because covariate availability
# differs by study. Stage is represented ordinally to avoid unstable sparse
# dummy variables in the smaller cohorts.
stage_number <- function(x) {
  x <- toupper(trimws(as.character(x)))
  x <- sub("^STAGE\\s*", "", x)
  out <- rep(NA_real_, length(x))
  out[grepl("^IV", x)] <- 4
  out[is.na(out) & grepl("^III", x)] <- 3
  out[is.na(out) & grepl("^II", x)] <- 2
  out[is.na(out) & grepl("^I", x)] <- 1
  numeric_stage <- suppressWarnings(as.numeric(sub("^([1-4]).*$", "\\1", x)))
  out[is.na(out) & numeric_stage %in% 1:4] <- numeric_stage[is.na(out) & numeric_stage %in% 1:4]
  out
}
grade_number <- function(x) {
  suppressWarnings(as.numeric(sub("^G([1-4]).*$", "\\1", toupper(trimws(as.character(x))))))
}

fit_adjusted_cohort <- function(x) {
  x$stage_number <- stage_number(x$stage)
  x$grade_number <- grade_number(x$grade)
  candidates <- c("age", "stage_number", "grade_number")
  usable <- candidates[vapply(candidates, function(v) {
    sum(is.finite(x[[v]])) >= 0.75 * nrow(x) &&
      length(unique(x[[v]][is.finite(x[[v]])])) > 1L
  }, logical(1))]
  if (!length(usable)) return(NULL)
  needed <- c("time_months", "event", "gprc5a_z", usable)
  complete <- stats::complete.cases(x[, needed, drop = FALSE])
  dat <- x[complete, , drop = FALSE]
  if (nrow(dat) < 30L || sum(dat$event) < 15L) return(NULL)
  form <- stats::as.formula(paste(
    "survival::Surv(time_months, event) ~ gprc5a_z +",
    paste(usable, collapse = " + ")
  ))
  fit <- survival::coxph(form, data = dat, ties = "efron", x = TRUE)
  sm <- summary(fit)
  ci <- stats::confint(fit)["gprc5a_z", ]
  data.frame(
    cohort = dat$cohort[1L], covariates = paste(usable, collapse = "+"),
    n = nrow(dat), events = sum(dat$event),
    hr_per_sd = unname(exp(stats::coef(fit)["gprc5a_z"])),
    ci_low = unname(exp(ci[1L])), ci_high = unname(exp(ci[2L])),
    p_value = sm$coefficients["gprc5a_z", "Pr(>|z|)"],
    ph_test_p = survival::cox.zph(fit)$table["gprc5a_z", "p"],
    stringsAsFactors = FALSE
  )
}
adjusted_results <- Filter(Negate(is.null), lapply(cohorts, fit_adjusted_cohort))
adjusted_results <- do.call(rbind, adjusted_results)
write.csv(adjusted_results, file.path(table_dir, "cohort_adjusted_sensitivity.csv"), row.names = FALSE)

g859_probe_sensitivity <- do.call(rbind, lapply(rownames(g859$values), function(probe) {
  probe_cohort <- make_cohort(
    paste0("GSE85916_", probe), "GPL13667 probe sensitivity",
    g859_id, as.numeric(g859_time) * 12, g859_event, g859$values[probe, ]
  )
  fit_one_cohort(probe_cohort)
}))
write.csv(g859_probe_sensitivity,
          file.path(table_dir, "gse85916_probe_sensitivity.csv"), row.names = FALSE)

# Exploratory diagnostic for the one cohort with evidence against proportional
# hazards. The 12-month cut is not a new primary endpoint and is reported only
# to show why a single constant HR is an imperfect summary in GSE62452.
Surv <- survival::Surv
g624_split <- survival::survSplit(
  Surv(time_months, event) ~ ., data = gse62452,
  cut = 12, episode = "period", id = "row_id"
)
g624_split$late <- as.integer(g624_split$period == 2L)
g624_time_fit <- survival::coxph(
  survival::Surv(tstart, time_months, event) ~ gprc5a_z * late + cluster(row_id),
  data = g624_split, ties = "efron"
)
g624_time_coef <- stats::coef(g624_time_fit)
g624_time_vcov <- stats::vcov(g624_time_fit)
early_log_hr <- unname(g624_time_coef["gprc5a_z"])
early_se <- sqrt(g624_time_vcov["gprc5a_z", "gprc5a_z"])
late_log_hr <- unname(g624_time_coef["gprc5a_z"] + g624_time_coef["gprc5a_z:late"])
late_se <- sqrt(
  g624_time_vcov["gprc5a_z", "gprc5a_z"] +
    g624_time_vcov["gprc5a_z:late", "gprc5a_z:late"] +
    2 * g624_time_vcov["gprc5a_z", "gprc5a_z:late"]
)
interaction_p <- summary(g624_time_fit)$coefficients["gprc5a_z:late", "Pr(>|z|)"]
non_ph_diagnostic <- data.frame(
  cohort = "GSE62452", period = c("0-12 months", ">12 months"),
  intervals = c(sum(g624_split$late == 0L), sum(g624_split$late == 1L)),
  events = c(sum(g624_split$event[g624_split$late == 0L]),
             sum(g624_split$event[g624_split$late == 1L])),
  hr_per_sd = exp(c(early_log_hr, late_log_hr)),
  ci_low = exp(c(early_log_hr - 1.96 * early_se, late_log_hr - 1.96 * late_se)),
  ci_high = exp(c(early_log_hr + 1.96 * early_se, late_log_hr + 1.96 * late_se)),
  time_interaction_p = interaction_p,
  analysis_status = "post-hoc proportional-hazards diagnostic",
  stringsAsFactors = FALSE
)
write.csv(non_ph_diagnostic,
          file.path(table_dir, "gse62452_non_ph_diagnostic.csv"), row.names = FALSE)

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

meta <- random_effects_reml(cox_results$log_hr, cox_results$se)
meta_table <- as.data.frame(as.list(meta), stringsAsFactors = FALSE)
write.csv(meta_table, file.path(table_dir, "random_effects_meta.csv"), row.names = FALSE)

loco <- do.call(rbind, lapply(seq_len(nrow(cox_results)), function(i) {
  estimate <- random_effects_reml(cox_results$log_hr[-i], cox_results$se[-i])
  data.frame(omitted = cox_results$cohort[i], as.list(estimate), check.names = FALSE)
}))
write.csv(loco, file.path(table_dir, "leave_one_cohort_out.csv"), row.names = FALSE)

# TCGA subtype interaction ----------------------------------------------------
moffitt_classical <- c(
  "BTNL8", "FAM83A", "CEACAM5", "CEACAM6", "LYZ", "TFF1", "TFF2", "TFF3",
  "LGALS4", "CYP3A7", "MYO1A", "CLRN3", "SLC40A1", "ANXA10", "CTSE",
  "AGR2", "ST6GALNAC1", "LOC400573", "VSIG2", "REG4", "LRRC26",
  "MSLN", "KRT20", "LTBP2", "CLDN18"
)
moffitt_basal <- c(
  "VGLL1", "UCA1", "S100A2", "LY6D", "LEMD1", "KRT15", "KRT17", "KRT19",
  "AREG", "SPRR1B", "SPRR2B", "CDKN2A", "ANLN", "FOXC2", "SCEL", "CSTA",
  "DSP", "EMP1", "LAMC2", "SERPINB13", "TNS4", "DYRK3", "FAT2", "TP63", "ST14"
)
symbols <- as.character(tcga_expr$Hugo_Symbol)
subtype_samples <- tcga$sample_id
available_classical <- intersect(moffitt_classical, symbols)
available_basal <- intersect(moffitt_basal, symbols)
get_gene_matrix <- function(genes) {
  idx <- match(genes, symbols)
  values <- as.matrix(tcga_expr[idx, subtype_samples, drop = FALSE])
  storage.mode(values) <- "double"
  values <- log2(values + 1)
  t(scale(t(values)))
}
classical_score <- colMeans(get_gene_matrix(available_classical), na.rm = TRUE)
basal_score <- colMeans(get_gene_matrix(available_basal), na.rm = TRUE)
tcga$subtype_score <- classical_score - basal_score
tcga$subtype <- factor(
  ifelse(tcga$subtype_score > 0, "Classical", "Basal_like"),
  levels = c("Basal_like", "Classical")
)
tcga$stage_advanced <- factor(
  ifelse(grepl("stage iii|stage iv", tolower(tcga$stage)), "Advanced", "Early"),
  levels = c("Early", "Advanced")
)
tcga$stage_number <- stage_number(tcga$stage)
interaction_fit <- survival::coxph(
  survival::Surv(time_months, event) ~ gprc5a_z * subtype + age + stage_number,
  data = tcga, ties = "efron"
)
interaction_sm <- summary(interaction_fit)
interaction_table <- data.frame(
  term = rownames(interaction_sm$coefficients),
  log_hr = interaction_sm$coefficients[, "coef"],
  hr = interaction_sm$coefficients[, "exp(coef)"],
  se = interaction_sm$coefficients[, "se(coef)"],
  p_value = interaction_sm$coefficients[, "Pr(>|z|)"],
  stringsAsFactors = FALSE
)
write.csv(interaction_table, file.path(table_dir, "tcga_subtype_interaction.csv"), row.names = FALSE)

subtype_results <- do.call(rbind, lapply(levels(tcga$subtype), function(st) {
  x <- tcga[tcga$subtype == st, ]
  fit_one_cohort(transform(x, cohort = paste0("TCGA_", st)))
}))
write.csv(subtype_results, file.path(table_dir, "tcga_subtype_cox.csv"), row.names = FALSE)

# GSE62452 tumour versus adjacent non-tumour ---------------------------------
g624_all$is_tumour <- tolower(g624_all$tissue) == "pancreatic tumor"
g624_compare <- g624_all[is.finite(g624_all$gprc5a), ]
group_test <- stats::wilcox.test(gprc5a ~ is_tumour, data = g624_compare, exact = FALSE)
group_effect <- mean(g624_compare$gprc5a[g624_compare$is_tumour]) -
  mean(g624_compare$gprc5a[!g624_compare$is_tumour])

pair_key <- function(title, tumour) {
  out <- as.character(title)
  out[tumour] <- sub("-?T[pc]?[0-9]*$", "", out[tumour], ignore.case = TRUE)
  out[!tumour] <- sub("-?Tn$", "", out[!tumour], ignore.case = TRUE)
  # Two deposited titles omit a leading zero (E12/E21 versus E012/E021).
  # Canonicalising the numeric part recovers the complete set of true pairs.
  e_sample <- grepl("^E0*[0-9]+", out, ignore.case = TRUE)
  e_number <- suppressWarnings(as.integer(sub(
    "^E0*([0-9]+).*$", "\\1", out[e_sample], ignore.case = TRUE
  )))
  out[e_sample] <- paste0("E", sprintf("%03d", e_number))
  out
}
g624_compare$pair_id <- pair_key(g624_compare$title, g624_compare$is_tumour)
tum <- g624_compare[g624_compare$is_tumour, c("pair_id", "gprc5a")]
nor <- g624_compare[!g624_compare$is_tumour, c("pair_id", "gprc5a")]
names(tum)[2L] <- "tumour"
names(nor)[2L] <- "normal"
pairs624 <- merge(tum, nor, by = "pair_id")
pairs624 <- pairs624[!duplicated(pairs624$pair_id), ]
paired_test <- stats::wilcox.test(pairs624$tumour, pairs624$normal, paired = TRUE, exact = FALSE)
g624_summary <- data.frame(
  comparison = c("all_samples_unpaired", "exact_patient_pairs"),
  n_tumour = c(sum(g624_compare$is_tumour), nrow(pairs624)),
  n_normal = c(sum(!g624_compare$is_tumour), nrow(pairs624)),
  mean_log2_difference = c(group_effect, mean(pairs624$tumour - pairs624$normal)),
  fold_change_from_mean_log2_difference = 2^c(
    group_effect, mean(pairs624$tumour - pairs624$normal)
  ),
  median_log2_difference = c(
    median(g624_compare$gprc5a[g624_compare$is_tumour]) -
      median(g624_compare$gprc5a[!g624_compare$is_tumour]),
    median(pairs624$tumour - pairs624$normal)
  ),
  p_value = c(group_test$p.value, paired_test$p.value),
  stringsAsFactors = FALSE
)
write.csv(g624_summary, file.path(table_dir, "gse62452_tumour_normal.csv"), row.names = FALSE)
write.csv(pairs624, file.path(table_dir, "gse62452_exact_pairs.csv"), row.names = FALSE)

# GSE164665 paired laser-capture cancer versus stroma -------------------------
read_count_matrix <- function(path) {
  # The GEO supplementary files have an intentionally blank first header and
  # repeated gene symbols.  Import the identifier column explicitly so base R
  # does not try (and fail) to turn duplicated symbols into row names.
  x <- read.delim(gzfile(path), check.names = FALSE)
  gene <- as.character(x[[1L]])
  x <- as.matrix(x[-1L])
  storage.mode(x) <- "numeric"
  rownames(x) <- make.unique(gene)
  x
}
cancer_counts <- read_count_matrix(file.path(cache_dir, "GSE164665_Cancer_raw_gene_counts.txt.gz"))
stroma_counts <- read_count_matrix(file.path(cache_dir, "GSE164665_Stroma_raw_gene_counts.txt.gz"))
cancer_ids <- sub("-T$", "", colnames(cancer_counts))
stroma_ids <- sub("-S$", "", colnames(stroma_counts))
shared_lcm <- intersect(cancer_ids, stroma_ids)
cancer_counts <- cancer_counts[, match(shared_lcm, cancer_ids), drop = FALSE]
stroma_counts <- stroma_counts[, match(shared_lcm, stroma_ids), drop = FALSE]
combined_counts <- cbind(cancer_counts, stroma_counts)
positive <- combined_counts > 0
geom_mean <- exp(rowSums(log(ifelse(positive, combined_counts, 1))) /
                   rowSums(positive))
valid_gene <- is.finite(geom_mean) & geom_mean > 0 & rowSums(positive) >= 2L
size_factor <- apply(combined_counts[valid_gene, , drop = FALSE], 2L, function(x) {
  ratio <- x / geom_mean[valid_gene]
  stats::median(ratio[is.finite(ratio) & ratio > 0])
})
normalized_counts <- sweep(combined_counts, 2L, size_factor, "/")
lcm_cancer <- log2(normalized_counts["GPRC5A", seq_along(shared_lcm)] + 1)
lcm_stroma <- log2(normalized_counts[
  "GPRC5A", length(shared_lcm) + seq_along(shared_lcm)
] + 1)
lcm_difference <- lcm_cancer - lcm_stroma
lcm_wilcox <- stats::wilcox.test(lcm_cancer, lcm_stroma, paired = TRUE, exact = FALSE)
lcm_ttest <- stats::t.test(lcm_cancer, lcm_stroma, paired = TRUE)
set.seed(20260912)
boot_mean <- replicate(5000L, mean(sample(lcm_difference, replace = TRUE)))
lcm_summary <- data.frame(
  pairs = length(shared_lcm),
  mean_cancer_log2_normalized = mean(lcm_cancer),
  mean_stroma_log2_normalized = mean(lcm_stroma),
  mean_paired_difference = mean(lcm_difference),
  fold_change_from_mean_log2_difference = 2^mean(lcm_difference),
  median_paired_difference = median(lcm_difference),
  bootstrap_ci_low = unname(stats::quantile(boot_mean, 0.025)),
  bootstrap_ci_high = unname(stats::quantile(boot_mean, 0.975)),
  paired_t_p = lcm_ttest$p.value,
  paired_wilcoxon_p = lcm_wilcox$p.value
)
write.csv(lcm_summary, file.path(table_dir, "gse164665_lcm_compartment.csv"), row.names = FALSE)
write.csv(
  data.frame(patient_id = shared_lcm, cancer = lcm_cancer, stroma = lcm_stroma,
             difference = lcm_difference),
  file.path(table_dir, "gse164665_lcm_pairs.csv"), row.names = FALSE
)

# CPTAC matched RNA-protein ---------------------------------------------------
protein_id <- as.character(cptac_protein[[1L]])
protein_row <- grep("^GPRC5A\\|", protein_id)[1L]
rna_samples <- names(cptac_expr)[-(1:2)]
protein_samples <- names(cptac_protein)[-1L]
matched_omics <- Reduce(intersect, list(
  rna_samples, protein_samples, cptac_clin$SAMPLE_ID
))
cptac_rna_gprc5a <- as.numeric(cptac_expr[cptac_row, matched_omics, drop = TRUE])
cptac_protein_gprc5a <- as.numeric(cptac_protein[protein_row, matched_omics, drop = TRUE])
complete_omics <- is.finite(cptac_rna_gprc5a) & is.finite(cptac_protein_gprc5a)
rna_protein_test <- stats::cor.test(
  cptac_rna_gprc5a[complete_omics], cptac_protein_gprc5a[complete_omics],
  method = "spearman", exact = FALSE
)
rna_protein <- data.frame(
  n = sum(complete_omics),
  spearman_rho = unname(rna_protein_test$estimate),
  p_value = rna_protein_test$p.value,
  stringsAsFactors = FALSE
)
write.csv(rna_protein, file.path(table_dir, "cptac_rna_protein.csv"), row.names = FALSE)
write.csv(
  data.frame(
    sample_id = matched_omics[complete_omics],
    rna = cptac_rna_gprc5a[complete_omics],
    protein = cptac_protein_gprc5a[complete_omics]
  ),
  file.path(table_dir, "cptac_rna_protein_pairs.csv"), row.names = FALSE
)

# Tumour composition can partly explain cohort-to-cohort expression effects.
# These correlations are descriptive and are not interpreted causally.
cptac_expression_for_composition <- as.numeric(
  cptac_expr[cptac_row, match(cptac_clin$SAMPLE_ID, names(cptac_expr)), drop = TRUE]
)
composition_results <- do.call(rbind, lapply(
  c("NEOPLASTIC_CELLULARITY", "STROMAL_FRACTION"),
  function(variable) {
    value <- suppressWarnings(as.numeric(cptac_clin[[variable]]))
    complete <- is.finite(value) & is.finite(cptac_expression_for_composition)
    test <- stats::cor.test(
      value[complete], cptac_expression_for_composition[complete],
      method = "spearman", exact = FALSE
    )
    data.frame(
      variable = variable, n = sum(complete),
      spearman_rho = unname(test$estimate), p_value = test$p.value,
      stringsAsFactors = FALSE
    )
  }
))
write.csv(
  composition_results,
  file.path(table_dir, "cptac_composition_correlations.csv"), row.names = FALSE
)

# Figures ---------------------------------------------------------------------
png(file.path(figure_dir, "forest_survival_meta.png"), width = 2100, height = 1200, res = 180)
par(mar = c(5, 14, 4, 2))
y <- rev(seq_len(nrow(cox_results))) + 1
meta_weights <- 1 / (cox_results$se^2 + meta["tau2"])
point_cex <- 0.8 + 0.8 * sqrt(meta_weights / max(meta_weights))
xlim <- range(c(cox_results$ci_low, c(meta["ci_low"], meta["ci_high"])), finite = TRUE)
xlim <- c(max(0.25, xlim[1] * 0.8), min(6, xlim[2] * 1.25))
plot(cox_results$hr_per_sd, y, log = "x", xlim = xlim, ylim = c(0.5, max(y) + 0.8),
     yaxt = "n", xlab = "Hazard ratio per within-cohort SD of GPRC5A",
     ylab = "", pch = 19, cex = point_cex,
     main = "GPRC5A and overall survival across PDAC cohorts")
segments(cox_results$ci_low, y, cox_results$ci_high, y, lwd = 2)
axis(2, at = y, labels = paste0(cox_results$cohort, "  (", cox_results$n, "; ",
                                 cox_results$events, " events)"), las = 1)
abline(v = 1, lty = 2, col = "grey50")
points(meta["hr"], 0.9, pch = 18, cex = 1.7, col = "#005B70")
segments(meta["ci_low"], 0.9, meta["ci_high"], 0.9, lwd = 3, col = "#005B70")
axis(2, at = 0.9, labels = "REML + Hartung-Knapp", las = 1, tick = FALSE)
mtext(sprintf("Pooled HR %.2f (95%% CI %.2f-%.2f); I2 %.1f%%; prediction interval %.2f-%.2f",
              meta["hr"], meta["ci_low"], meta["ci_high"], meta["i2_percent"],
              meta["prediction_low"], meta["prediction_high"]), side = 3, line = 0.3, cex = 0.85)
dev.off()

png(file.path(figure_dir, "compartment_expression.png"), width = 1800, height = 900, res = 180)
par(mfrow = c(1, 2), mar = c(5, 5, 4, 1))
matplot(t(as.matrix(pairs624[, c("normal", "tumour")])), type = "l", lty = 1,
        col = rgb(0.2, 0.2, 0.2, 0.25), xaxt = "n", xlab = "", ylab = "GPRC5A expression",
        main = sprintf("GSE62452 exact pairs (n=%d)", nrow(pairs624)))
axis(1, at = 1:2, labels = c("Adjacent", "Tumour"))
points(rep(1, nrow(pairs624)), pairs624$normal, pch = 16, col = "#4D7EA8")
points(rep(2, nrow(pairs624)), pairs624$tumour, pch = 16, col = "#B33A3A")
mtext(sprintf("paired Wilcoxon p = %.3g", paired_test$p.value), side = 3, line = 0.2, cex = 0.8)
matplot(rbind(lcm_stroma, lcm_cancer), type = "l", lty = 1,
        col = rgb(0.2, 0.2, 0.2, 0.3), xaxt = "n", xlab = "",
        ylab = "log2 median-ratio normalized count + 1",
        main = sprintf("GSE164665 laser-capture pairs (n=%d)", length(shared_lcm)))
axis(1, at = 1:2, labels = c("Stroma", "Cancer"))
points(rep(1, length(shared_lcm)), lcm_stroma, pch = 16, col = "#587D58")
points(rep(2, length(shared_lcm)), lcm_cancer, pch = 16, col = "#B33A3A")
mtext(sprintf("paired Wilcoxon p = %.3g", lcm_wilcox$p.value), side = 3, line = 0.2, cex = 0.8)
dev.off()

png(file.path(figure_dir, "cptac_rna_protein.png"), width = 1100, height = 1000, res = 180)
plot(cptac_rna_gprc5a[complete_omics], cptac_protein_gprc5a[complete_omics],
     pch = 19, col = rgb(0, 0.35, 0.45, 0.55),
     xlab = "CPTAC GPRC5A RNA abundance", ylab = "CPTAC GPRC5A protein abundance",
     main = "Matched GPRC5A RNA and protein")
abline(stats::lm(cptac_protein_gprc5a[complete_omics] ~
                   cptac_rna_gprc5a[complete_omics]), col = "#B33A3A", lwd = 2)
legend("topleft", bty = "n",
       legend = sprintf("Spearman rho = %.3f; n = %d", rna_protein$spearman_rho, rna_protein$n))
dev.off()

# Fail loudly if a parser, eligibility rule, or upstream file changes.
stopifnot(
  identical(unname(cohort_flow$patients), c(145L, 129L, 79L, 63L, 65L)),
  identical(unname(cohort_flow$events), c(84L, 72L, 57L, 42L, 49L)),
  all(vapply(cohorts, function(x) all(x$specimen_class == "primary_tumor"), logical(1))),
  nrow(pairs624) == 45L,
  length(shared_lcm) == 19L,
  rna_protein$n == 135L,
  all(is.finite(cox_results$log_hr)),
  "gprc5a_z:subtypeClassical" %in% interaction_table$term
)

writeLines(
  c(
    "GPRC5A PDAC v2 run manifest",
    paste("Generated:", format(Sys.time(), tz = "UTC", usetz = TRUE)),
    paste("R:", R.version.string),
    paste("Cohorts:", paste(names(cohorts), collapse = ", ")),
    paste("Patients:", sum(cohort_flow$patients)),
    paste("Events:", sum(cohort_flow$events)),
    paste("Pooled HR:", signif(meta["hr"], 4)),
    paste("Pooled 95% CI:", paste(signif(meta[c("ci_low", "ci_high")], 4), collapse = " to ")),
    paste("I2:", signif(meta["i2_percent"], 4)),
    "No cross-platform harmonization was performed."
  ),
  file.path(result_dir, "run_manifest.txt")
)

message("Version 2 analysis complete")
print(cohort_flow, row.names = FALSE)
print(cox_results[, c("cohort", "n", "events", "hr_per_sd", "ci_low", "ci_high", "p_value")], row.names = FALSE)
print(meta_table, row.names = FALSE)
