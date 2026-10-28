## Plan: seqkit stats

- **Tool dir:** `seqkit_stats`, one tool `seqkit_stats.xml`.
- **Requirement:** `seqkit` from bioconda (latest version).
- **Inputs:** one or more FASTA/FASTQ datasets (`fasta`, `fastqsanger`, and their `.gz` variants).
- **Options:** `--all` (boolean, all statistics); always write tabular output (`-T`).
- **Output:** one `tabular` dataset.
- **Tests:** a small FASTA in `test-data/`; check the output with `has_text` and `has_n_columns`.
- **Help:** a short description with a link to https://bioinf.shenwei.me/seqkit/usage/#stats.
- **Citation:** DOI `10.1371/journal.pone.0163962`.
- **Shed:** `.shed.yml` with owner `arash77`, category "Sequence Analysis".
