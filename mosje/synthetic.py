"""Seeded synthetic data: Jan Aadhaar (Rajasthan) members + CBSE 2025-26 pass-out cohort.

Everything here is fictional. Output (CSV, in data/):
    jan_aadhaar_members.csv, cbse_passed_2025_26.csv, ground_truth.csv
"""
from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

from . import config

DISTRICTS = ["Ajmer", "Alwar", "Banswara", "Baran", "Barmer", "Bharatpur", "Bhilwara", "Bikaner",
             "Bundi", "Chittorgarh", "Churu", "Dausa", "Dholpur", "Dungarpur", "Hanumangarh",
             "Jaipur", "Jaisalmer", "Jalore", "Jhalawar", "Jhunjhunu", "Jodhpur", "Karauli", "Kota",
             "Nagaur", "Pali", "Pratapgarh", "Rajsamand", "Sawai Madhopur", "Sikar", "Sirohi",
             "Sri Ganganagar", "Tonk", "Udaipur"]
# ST-heavy southern districts
ST_DISTRICTS = ["Banswara", "Dungarpur", "Udaipur", "Pratapgarh", "Sirohi", "Dausa", "Sawai Madhopur", "Karauli"]

MALE = ["Aarav", "Rohan", "Rahul", "Amit", "Vikram", "Suresh", "Mahesh", "Rajesh", "Ramesh", "Mukesh",
        "Dinesh", "Naresh", "Sunil", "Anil", "Ajay", "Vijay", "Sanjay", "Manoj", "Deepak", "Pankaj",
        "Ankit", "Ashok", "Gopal", "Govind", "Harish", "Hemant", "Jitendra", "Kailash", "Lokesh",
        "Mohan", "Narendra", "Prakash", "Pradeep", "Rakesh", "Ravi", "Sachin", "Sandeep", "Satish",
        "Shyam", "Vikas", "Yash", "Aditya", "Arjun", "Dev", "Kunal", "Lakshya", "Nikhil", "Pranav",
        "Rohit", "Sahil", "Tarun", "Uday", "Vishal", "Karan", "Kapil", "Bhavesh", "Chetan", "Dilip",
        "Girish", "Hitesh", "Jagdish", "Kishan", "Lalit", "Mahendra", "Nitin", "Pawan", "Raju",
        "Sohan", "Umesh", "Bharat", "Devendra", "Ganesh", "Himanshu", "Ishaan", "Jayesh", "Kamal",
        "Laxman", "Madan", "Naveen", "Prem", "Rajendra", "Shankar", "Surendra", "Tushar", "Virendra",
        "Harsh", "Mayank", "Gaurav", "Abhishek", "Ritik", "Vivek", "Shubham", "Aman", "Dheeraj"]
FEMALE = ["Priya", "Pooja", "Poonam", "Neha", "Sunita", "Anita", "Kavita", "Savita", "Rekha", "Suman",
          "Manju", "Seema", "Geeta", "Sita", "Radha", "Kiran", "Asha", "Usha", "Nisha", "Ritu",
          "Mamta", "Sarita", "Lalita", "Kamla", "Santosh", "Shanti", "Laxmi", "Durga", "Aarti",
          "Ankita", "Divya", "Jyoti", "Komal", "Khushi", "Mansi", "Nikita", "Payal", "Riya", "Sakshi",
          "Shivani", "Sneha", "Tanvi", "Varsha", "Anjali", "Bhavna", "Chanchal", "Deepika", "Gunjan",
          "Himani", "Isha", "Jaya", "Kajal", "Lata", "Monika", "Namrata", "Pallavi", "Rachna", "Sapna",
          "Tanu", "Vandana", "Yamini", "Aishwarya", "Diksha", "Kritika", "Muskan", "Palak", "Rashmi",
          "Sonam", "Vaishali", "Pinki", "Mona", "Hema", "Pushpa", "Kanta", "Bhagwati", "Gayatri"]
M_MALE = ["Imran", "Salman", "Irfan", "Arif", "Aamir", "Faisal", "Javed", "Rashid", "Sajid", "Shahid",
          "Wasim", "Yusuf", "Zaid", "Rizwan", "Nadeem", "Sameer", "Tariq", "Asif", "Farhan", "Ayaan",
          "Arman", "Rehan", "Sohail", "Junaid", "Shoaib", "Aslam", "Iqbal", "Anwar", "Akram", "Saleem"]
M_FEMALE = ["Ayesha", "Fatima", "Zainab", "Sana", "Nazia", "Rukhsar", "Shabana", "Rubina", "Farzana",
            "Heena", "Nasreen", "Shahnaz", "Salma", "Tabassum", "Mehnaz", "Afreen", "Alfiya", "Sadia",
            "Zoya", "Samina", "Reshma", "Parveen"]
S_MALE = ["Gurpreet", "Harpreet", "Manpreet", "Jaspreet", "Sukhwinder", "Baljeet", "Amandeep", "Gurmeet"]
S_FEMALE = ["Harleen", "Simran", "Jasleen", "Manjeet", "Kulwinder", "Navneet", "Rajwinder", "Gurleen"]

SURNAMES = {
    "SC": ["Meghwal", "Jatav", "Bairwa", "Regar", "Balai", "Koli", "Khatik", "Raigar", "Nayak", "Verma"],
    "ST": ["Meena", "Meena", "Meena", "Bhil", "Garasia", "Damor", "Sahariya", "Ninama", "Bhagora", "Katara"],
    "OBC": ["Jat", "Choudhary", "Yadav", "Saini", "Kumawat", "Gurjar", "Mali", "Prajapat", "Suthar",
            "Jangid", "Sen", "Swami", "Dhaka", "Godara", "Beniwal", "Bishnoi", "Sharma", "Mahawar"],
    "General": ["Sharma", "Agarwal", "Jain", "Rathore", "Shekhawat", "Joshi", "Purohit", "Mathur",
                "Gupta", "Bhati", "Vyas", "Tiwari", "Mishra", "Goyal", "Maheshwari", "Singh"],
    "Minority": ["Khan", "Qureshi", "Ansari", "Sheikh", "Pathan", "Rangrez", "Mansuri", "Siddiqui"],
}
CATEGORY_MIX = [("SC", 0.18), ("ST", 0.14), ("OBC", 0.46), ("General", 0.13), ("Minority", 0.09)]
SIMILAR_FIRST = {"Priya": "Piya", "Rohan": "Rohit", "Aarav": "Arav", "Neha": "Nehal", "Aman": "Amar",
                 "Riya": "Siya", "Karan": "Kiran", "Yash": "Yashu", "Sonam": "Sonal", "Ritu": "Rita",
                 "Payal": "Pallavi", "Rahul": "Rahil", "Ankit": "Ankur", "Nikhil": "Nikhilesh",
                 "Divya": "Diya", "Tanvi": "Tanya", "Arjun": "Arun", "Sahil": "Sohil", "Kajal": "Komal"}
SCHOOLS = ["Kendriya Vidyalaya No. {n}", "DAV Public School", "Delhi Public School", "St. Xavier's School",
           "Jawahar Navodaya Vidyalaya", "Sophia Senior Secondary School", "Maheshwari Public School",
           "Army Public School", "Ryan International School", "Mayoor School", "Tagore Public School",
           "Seedling Public School", "Modern School", "Central Academy"]
DOB_FORMATS = ["%d-%m-%Y", "%d/%m/%Y", "%d %b %Y"]


class Gen:
    def __init__(self, seed=config.SEED):
        self.r = random.Random(seed)
        self.jid = 0
        self.mid = 0

    # ---------------------------------------------------------- helpers
    def pick(self, seq):
        return self.r.choice(seq)

    def category(self):
        x, acc = self.r.random(), 0.0
        for c, p in CATEGORY_MIX:
            acc += p
            if x < acc:
                return c
        return "OBC"

    def mobile(self):
        return self.pick("6789") + "".join(self.pick("0123456789") for _ in range(9))

    def rand_date(self, start: date, end: date) -> date:
        return start + timedelta(days=self.r.randint(0, (end - start).days))

    def income(self, cat):
        base = {"SC": 110000, "ST": 95000, "OBC": 150000, "General": 260000, "Minority": 140000}[cat]
        v = self.r.lognormvariate(0, 0.7) * base
        return int(round(min(max(v, 24000), 2500000), -3))

    def is_sikh(self, cat, sikh_flag):
        return cat == "Minority" and sikh_flag

    def male_name(self, cat, surname, sikh=False, adult=False):
        if cat == "Minority" and not sikh:
            first = self.pick(M_MALE)
            pre = "Mohammad " if self.r.random() < (0.45 if adult else 0.35) else ""
            return f"{pre}{first} {surname}"
        if sikh:
            return f"{self.pick(S_MALE)} Singh"
        first = self.pick(MALE)
        mid = ""
        x = self.r.random()
        if x < 0.22:
            mid = " Kumar"
        elif adult and x < 0.30:
            mid = self.pick([" Lal", " Prasad", " Chand", " Ram"])
        if self.r.random() < 0.06:
            return f"{first}{mid or ' Kumar'}"
        return f"{first}{mid} {surname}"

    def female_name(self, cat, surname, sikh=False, adult=False):
        if cat == "Minority" and not sikh:
            first = self.pick(M_FEMALE)
            suf = self.pick(["Bano", "Begum", surname]) if adult else self.pick(["Bano", surname, surname])
            return f"{first} {suf}"
        if sikh:
            return f"{self.pick(S_FEMALE)} Kaur"
        first = self.pick(FEMALE)
        if adult:
            return f"{first} {'Devi' if self.r.random() < 0.55 else surname}"
        return f"{first} {'Kumari' if self.r.random() < 0.3 else surname}"

    # ---------------------------------------------------------- Jan Aadhaar
    def new_member(self, jid, name, dob, gender, father, mother, cat, income, district, mobile, relation):
        self.mid += 1
        disability = "Yes" if self.r.random() < 0.02 else "No"
        return {
            "jan_aadhaar_id": jid, "member_id": f"M{self.mid:07d}", "nameEng": name, "nameHnd": "",
            "dob": dob.strftime("%d-%m-%Y"), "gender": gender, "fatherNameEng": father,
            "motherNameEng": mother, "category": cat, "annual_family_income": income,
            "district": district, "domicile_state": "Rajasthan", "disability": disability,
            "mobile": mobile, "relation": relation,
        }

    def family(self, forced=None):
        """Create one family. `forced` builds a near-lookalike family of an existing one."""
        self.jid += 1
        jid = f"JA{self.jid:08d}"
        r = self.r
        if forced:
            cat, surname, sikh = forced["cat"], forced["surname"], forced["sikh"]
        else:
            cat = self.category()
            sikh = cat == "Minority" and r.random() < 0.12
            surname = self.pick(SURNAMES[cat])
        district = self.pick(ST_DISTRICTS) if cat == "ST" and r.random() < 0.7 else self.pick(DISTRICTS)
        income = self.income(cat)
        if r.random() < 0.01:
            income = None  # missing income in source -> tests unresolvable-student-data path
        cat_value = cat if r.random() > 0.005 else ""  # rare missing category
        fam_mobile = self.mobile()
        if forced:
            father, mother = forced["father"], forced["mother"]
        else:
            father = self.male_name(cat, surname, sikh, adult=True)
            mother = self.female_name(cat, surname, sikh, adult=True)
        f_dob = self.rand_date(date(1966, 1, 1), date(1988, 12, 31))
        m_dob = f_dob + timedelta(days=r.randint(365, 6 * 365))
        members = []
        gp = lambda: self.male_name(cat, surname, sikh, adult=True)
        members.append(self.new_member(jid, father, f_dob, "Male", gp(),
                                       self.female_name(cat, surname, sikh, adult=True), cat_value,
                                       income, district, fam_mobile, "Head"))
        other_sur = self.pick(SURNAMES[cat])
        members.append(self.new_member(jid, mother, m_dob, "Female", self.male_name(cat, other_sur, sikh, True),
                                       self.female_name(cat, other_sur, sikh, True), cat_value, income,
                                       district, "" if r.random() < 0.5 else self.mobile(), "Spouse"))
        children = []
        if forced:
            specs = [(forced["child_dob"], forced["child_gender"], forced["child_name"])]
        else:
            n = r.choices([1, 2, 3, 4], [0.22, 0.45, 0.24, 0.09])[0]
            if r.random() < 0.88:
                anchor = self.rand_date(date(2007, 7, 1), date(2011, 6, 30))
            else:
                anchor = self.rand_date(date(2001, 1, 1), date(2018, 12, 31))
            earliest = m_dob + timedelta(days=19 * 365)
            if anchor < earliest:
                anchor = earliest + timedelta(days=r.randint(0, 900))
            dobs = [anchor]
            for _ in range(n - 1):
                d = anchor + timedelta(days=r.choice([-1, 1]) * r.randint(420, 2200))
                if d > earliest and d < date(2021, 1, 1):
                    dobs.append(d)
            specs = []
            used = set()
            for d in dobs:
                g = "Male" if r.random() < 0.52 else "Female"
                for _ in range(10):
                    nm = self.male_name(cat, surname, sikh) if g == "Male" else self.female_name(cat, surname, sikh)
                    if nm.split()[0] not in used:
                        break
                used.add(nm.split()[0])
                specs.append((d, g, nm))
            # twins (same DOB, same parents, similar or different name)
            if r.random() < 0.05:
                d, g, nm = specs[0]
                first = nm.split()[0]
                tg = g if r.random() < 0.65 else ("Female" if g == "Male" else "Male")
                if tg == g and first in SIMILAR_FIRST:
                    tn = nm.replace(first, SIMILAR_FIRST[first], 1)
                else:
                    for _ in range(10):
                        tn = self.male_name(cat, surname, sikh) if tg == "Male" else self.female_name(cat, surname, sikh)
                        if tn.split()[0] != first:
                            break
                specs.append((d, tg, tn))
        for d, g, nm in specs:
            m = self.new_member(jid, nm, d, g, father, mother, cat_value, income, district,
                                fam_mobile if r.random() < 0.8 else self.mobile(), "Child")
            members.append(m)
            children.append(m)
        meta = {"cat": cat, "surname": surname, "sikh": sikh, "father": father, "mother": mother}
        return members, children, meta


# ---------------------------------------------------------------- noise functions
def _spelling_variant(r: random.Random, name: str) -> str:
    rules = [("sh", "s"), ("oo", "u"), ("aa", "a"), ("ee", "i"), ("v", "w"), ("ph", "f"), ("ya", "ia"),
             ("i", "ee"), ("u", "oo"), ("a", "aa"), ("th", "t"), ("dh", "d"), ("kh", "k")]
    low = name.lower()
    r.shuffle(rules)
    edits = r.choice([1, 1, 2])
    out = name
    done = 0
    for a, b in rules:
        idx = out.lower().find(a, 1)
        if idx > 0:
            seg = out[idx:idx + len(a)]
            rep = b.upper() if seg.isupper() else b
            out = out[:idx] + rep + out[idx + len(a):]
            done += 1
            if done >= edits:
                break
    if out == name and len(name) > 4:  # fallback: drop one interior letter
        i = r.randint(1, len(name) - 2)
        if name[i] != " ":
            out = name[:i] + name[i + 1:]
    return out


def _initialise_middle(name: str):
    toks = name.split()
    if len(toks) >= 3:
        toks[1] = toks[1][0]
        return " ".join(toks)
    return None


def _mohd(r, name):
    if "Mohammad" in name:
        return name.replace("Mohammad", r.choice(["Mohd", "Md", "Mohd.", "Mohammed", "Md."]), 1)
    return None


def _parent_variant(r, name):
    toks = name.split()
    opts = []
    if len(toks) >= 2 and toks[-1] in ("Devi", "Bano", "Begum"):
        opts.append(" ".join(toks[:-1]))
    if len(toks) >= 3:
        opts.append(" ".join([toks[0], toks[-1]]))
    if len(toks) >= 2:
        opts.append(toks[0])
    opts.append(_spelling_variant(r, name))
    return r.choice(opts)


def _dob_error(r, d: date) -> date:
    x = r.random()
    if x < 0.35 and d.day <= 12 and d.day != d.month:
        return date(d.year, d.day, d.month)
    if x < 0.75:
        return d + timedelta(days=r.choice([-3, -2, -1, 1, 2, 3]))
    try:
        return d.replace(year=d.year + r.choice([-1, 1]))
    except ValueError:
        return d + timedelta(days=365)


def _surface(r, text: str, upper: bool) -> str:
    return text.upper() if upper else text


def generate(out_dir: Path = None, seed: int = config.SEED):
    out_dir = Path(out_dir or config.DATA_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    g = Gen(seed)
    r = g.r
    members, children, metas = [], [], []
    for _ in range(config.N_FAMILIES):
        m, c, meta = g.family()
        members += m
        children += [(x, meta) for x in c]
    # ---- near-lookalike families: same child DOB+gender, similar parents & child name
    cohort_children = [(c, meta) for c, meta in children
                       if date(2007, 7, 1) <= _d(c["dob"]) <= date(2011, 6, 30)]
    n_look = 220
    lookalike_of = {}
    for c, meta in r.sample(cohort_children, n_look):
        mode = r.random()
        father = meta["father"] if mode < 0.5 else _spelling_variant(r, meta["father"])
        mother = meta["mother"] if mode > 0.3 else _spelling_variant(r, meta["mother"])
        first = c["nameEng"].split()[0]
        cname = (c["nameEng"].replace(first, SIMILAR_FIRST[first], 1) if first in SIMILAR_FIRST
                 else _spelling_variant(r, c["nameEng"]))
        forced = dict(meta, father=father, mother=mother, child_dob=_d(c["dob"]),
                      child_gender=c["gender"], child_name=cname)
        m, cc, meta2 = g.family(forced)
        members += m
        lookalike_of[cc[0]["member_id"]] = c["member_id"]

    # ---- CBSE cohort
    x_pool = [c for c, _ in children if date(2009, 7, 1) <= _d(c["dob"]) <= date(2011, 6, 30)]
    xii_pool = [c for c, _ in children if date(2007, 7, 1) <= _d(c["dob"]) <= date(2009, 6, 30)]
    n_x_in = round(config.N_CBSE_X * config.SHARE_IN_JAN_AADHAAR)
    n_xii_in = round(config.N_CBSE_XII * config.SHARE_IN_JAN_AADHAAR)
    assert len(x_pool) >= n_x_in and len(xii_pool) >= n_xii_in, (len(x_pool), len(xii_pool))
    fam_by_mid = {c["member_id"]: meta for c, meta in children}
    chosen = [(c, "X") for c in r.sample(x_pool, n_x_in)] + [(c, "XII") for c in r.sample(xii_pool, n_xii_in)]
    ja_by_jid_head = {m["jan_aadhaar_id"]: m for m in members if m["relation"] == "Head"}

    cbse, truth = [], []
    roll_seen = set()

    def new_roll():
        while True:
            v = str(r.randint(10_000_000, 99_999_999))
            if v not in roll_seen:
                roll_seen.add(v)
                return v

    def emit(name, dob, gender, father, mother, cls, district, mobile, true_mid, noise):
        upper = r.random() < 0.5
        fmt = r.choice(DOB_FORMATS)
        gcode = {"Male": r.choice(["M", "Male", "MALE"]), "Female": r.choice(["F", "Female", "FEMALE"])}[gender]
        school = r.choice(SCHOOLS).format(n=r.randint(1, 5)) + f", {district}"
        roll = new_roll()
        cbse.append({
            "roll_no": roll, "apaar_id": "".join(r.choice("0123456789") for _ in range(12)),
            "candidate_name": _surface(r, name, upper), "dob": dob.strftime(fmt), "gender": gcode,
            "father_name": _surface(r, father, upper), "mother_name": _surface(r, mother, upper),
            "class_passed": cls, "school": school, "district": district, "mobile": mobile,
        })
        truth.append({"roll_no": roll, "true_member_id": true_mid or "",
                      "in_jan_aadhaar": "Y" if true_mid else "N", "class_passed": cls,
                      "noise_types": ";".join(noise) if noise else ("clean_l1" if true_mid else "not_in_jan_aadhaar"),
                      "has_lookalike_or_twin": ""})

    for c, cls in chosen:
        name, father, mother = c["nameEng"], c["fatherNameEng"], c["motherNameEng"]
        dob = _d(c["dob"])
        noise = []
        m = _mohd(r, name) if r.random() < 0.75 else None
        if m:
            name = m; noise.append("mohd_variant")
        mf = _mohd(r, father) if r.random() < 0.6 else None
        if mf:
            father = mf; noise.append("mohd_variant_father") if "mohd_variant" not in noise else None
        x = r.random()
        if x < 0.08 and len(name.split()) >= 2:
            toks = name.split()
            name = " ".join(toks[1:] + toks[:1]); noise.append("reversed_order")
        elif x < 0.21:
            name = _spelling_variant(r, name); noise.append("spelling_variant")
        elif x < 0.28:
            v = _initialise_middle(name)
            if v:
                name = v; noise.append("missing_initial")
            else:
                v = _initialise_middle(father)
                if v:
                    father = v; noise.append("missing_initial_father")
        if r.random() < 0.13:
            if r.random() < 0.5:
                father = _parent_variant(r, father)
            else:
                mother = _parent_variant(r, mother)
            if r.random() < 0.15:  # both parents differ
                mother = _parent_variant(r, mother)
            noise.append("parent_discrepancy")
        if r.random() < 0.06:
            name = name.replace(" ", "  ", 1) if r.random() < 0.5 else name + " ."
            noise.append("space_punct")
        if r.random() < 0.04:
            dob = _dob_error(r, dob); noise.append("dob_error")
        head = ja_by_jid_head[c["jan_aadhaar_id"]]
        mob = head["mobile"] if r.random() < 0.6 else g.mobile()
        if r.random() < 0.02:
            mob = r.choice(["", "12345", "0000000000"])
        district = c["district"] if r.random() < 0.9 else r.choice(DISTRICTS)
        emit(name, dob, c["gender"], father, mother, cls, district, mob, c["member_id"], noise)

    # ---- CBSE students with no Jan Aadhaar record
    for cls, n_total, n_in, lo, hi in (("X", config.N_CBSE_X, n_x_in, date(2009, 7, 1), date(2011, 6, 30)),
                                       ("XII", config.N_CBSE_XII, n_xii_in, date(2007, 7, 1), date(2009, 6, 30))):
        for _ in range(n_total - n_in):
            cat = g.category()
            sikh = cat == "Minority" and r.random() < 0.12
            sur = g.pick(SURNAMES[cat])
            gender = "Male" if r.random() < 0.52 else "Female"
            name = g.male_name(cat, sur, sikh) if gender == "Male" else g.female_name(cat, sur, sikh)
            father = g.male_name(cat, sur, sikh, adult=True)
            mother = g.female_name(cat, sur, sikh, adult=True)
            mob = g.mobile() if r.random() > 0.02 else ""
            emit(name, g.rand_date(lo, hi), gender, father, mother, cls, g.pick(DISTRICTS), mob, None, [])

    # shuffle CBSE order (stable by seed)
    order = list(range(len(cbse)))
    r.shuffle(order)
    cbse = [cbse[i] for i in order]
    truth = [truth[i] for i in order]

    # flag records whose true member has a same-DOB sibling/lookalike in JA
    by_dob_gender = {}
    for m in members:
        by_dob_gender.setdefault((m["dob"], m["gender"]), []).append(m)
    mid_map = {m["member_id"]: m for m in members}
    for t in truth:
        if t["true_member_id"]:
            m = mid_map[t["true_member_id"]]
            peers = [p for p in by_dob_gender[(m["dob"], m["gender"])] if p["member_id"] != m["member_id"]
                     and (p["jan_aadhaar_id"] == m["jan_aadhaar_id"] or p["member_id"] in lookalike_of)]
            t["has_lookalike_or_twin"] = "Y" if peers else "N"

    _write(out_dir / "jan_aadhaar_members.csv", members)
    _write(out_dir / "cbse_passed_2025_26.csv", cbse)
    _write(out_dir / "ground_truth.csv", truth)
    return {"jan_aadhaar_members": len(members), "families": g.jid, "lookalike_families": n_look,
            "cbse_records": len(cbse), "cbse_in_ja": sum(1 for t in truth if t["true_member_id"])}


def _d(s: str) -> date:
    dd, mm, yy = s.split("-")
    return date(int(yy), int(mm), int(dd))


def _write(path: Path, rows: list[dict]):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    print(generate())
