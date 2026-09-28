# Data dictionary: upload files

Two files can be uploaded (dashboard **Admin** tab, or `/docs` in the API). Each upload **replaces** that
table. The column names are the same as in the bundled synthetic files (`data/*.csv.gz`) and the templates
in this folder. Upper/lower case, spaces and underscores in column names do not matter
(`Roll No` = `roll_no`). Extra columns are ignored (you get a warning).

**Required** column: must be in the file. **Must be filled**: every row needs a value.
**Optional**: the column may be left out; blank values are fine.

File types: `.csv` (save from Excel as *CSV UTF-8*), `.csv.gz`, or `.xlsx` (first sheet is read).

Dates (`dob`) are accepted as `2009-04-07`, `07-04-2009`, `07/04/2009`, `07.04.2009`, `07 Apr 2009`,
`07 April 2009`, `07-Apr-2009`, `2009/04/07` or an Excel date cell. Day comes before month. Dates must be
between 1900 and today.

Gender is accepted as `Male`/`Female`/`Transgender`/`Other` or `M`/`F`/`T`/`O`, any case (also `boy`/`girl`).

## 1. CBSE passed students: `cbse_template.csv`

One row per student who passed Class X or XII.

| Column | Required? | Format | Example |
|---|---|---|---|
| `roll_no` | Required, must be filled, unique | Text (roll number) | `90000001` |
| `apaar_id` | Optional | Text (12 digits) | `100000000001` |
| `candidate_name` | Required, must be filled | Text, as on the marksheet | `TEST STUDENT ONE` |
| `dob` | Required, must be filled | Date (see formats above) | `07 Apr 2009` |
| `gender` | Required, must be filled | Male / Female / Transgender / Other or M / F / T / O | `Female` |
| `father_name` | Required (value may be blank) | Text | `TEST FATHER ONE` |
| `mother_name` | Required (value may be blank) | Text | `TEST MOTHER ONE` |
| `class_passed` | Required, must be filled | `X` or `XII` (`10`, `12`, `Class X` also accepted; stored as X / XII) | `XII` |
| `school` | Optional | Text | `Example Public School, Jaipur` |
| `district` | Optional | Text | `Jaipur` |
| `mobile` | Optional | 10-digit mobile (invalid numbers are kept but not used for messages) | `9000000001` |

## 2. Jan Aadhaar members: `jan_aadhaar_template.csv`

One row per family member.

| Column | Required? | Format | Example |
|---|---|---|---|
| `jan_aadhaar_id` | Required, must be filled | Text (family ID) | `JA90000001` |
| `member_id` | Required, must be filled, unique | Text (member ID) | `M90000001` |
| `nameEng` | Required, must be filled | Text (name in English) | `Test Student One` |
| `nameHnd` | Optional | Text (name in Hindi, not used for matching) | *(blank)* |
| `dob` | Required, must be filled | Date (see formats above) | `07-04-2009` |
| `gender` | Required, must be filled | Male / Female / Transgender / Other or M / F / T / O (stored as `Male`, `Female`, ...) | `Female` |
| `fatherNameEng` | Required (value may be blank) | Text | `Test Father One` |
| `motherNameEng` | Required (value may be blank) | Text | `Test Mother One` |
| `category` | Required (value may be blank) | `SC`, `ST`, `OBC`, `General` or `Minority` (any case). Other values are kept with a warning; schemes limited to a category treat them as not matching. Blank = unknown (fails category-limited schemes) | `SC` |
| `annual_family_income` | Required (value may be blank) | Whole rupees; commas and `Rs`/`₹` are removed (`1,20,000` → `120000`). Blank = unknown (fails income-limited schemes) | `120000` |
| `district` | Optional | Text | `Jaipur` |
| `domicile_state` | Required (value may be blank) | State name as in the scheme master, e.g. `Rajasthan`. Blank = only Central schemes can match | `Rajasthan` |
| `disability` | Optional | `Yes` / `No` | `No` |
| `mobile` | Optional | 10-digit mobile | `9000000001` |
| `relation` | Optional | `Head` / `Spouse` / `Child` / ... | `Child` |

## What makes a file fail

The whole file is rejected (nothing changes) if a required column is missing, a column name appears twice,
or any row has a problem: an empty must-fill value, a date that is not a date, an unknown gender, a class that
is not X/XII, an income that is not a number, or a duplicate `roll_no` / `member_id`. The error lists the
number of bad rows per problem and the first 10 bad rows with their line numbers (header = line 1).

## Ground truth

The synthetic data comes with a *ground truth* file (the correct match for every student), which is used to
calculate precision, recall and TP/FP/FN. Real data has no ground truth, so after an upload these numbers
show **"not available (no ground truth)"**. **POST /admin/seed** restores the synthetic data and its ground truth.

> **Never upload real government personal data to Render or GitHub.** Use anonymised or synthetic data only.
> Real data must stay on NIC / MeghRaj infrastructure.
