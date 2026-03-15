# parse_cv.py
#
# Reusable CV parser — called by app.py when user uploads a .docx
# Input:  path to .docx file
# Output: cv dict (same structure as before)

import json
import re
from pathlib import Path
from docx import Document


def extract_text_blocks(doc) -> list[dict]:
    """Extract all non-empty paragraphs with their style."""
    blocks = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            blocks.append({
                "text":  text,
                "style": para.style.name
            })
    return blocks


def find_section(blocks, section_name) -> list[str]:
    """Find all bullet points under a section heading."""
    result = []
    inside = False
    for b in blocks:
        if b["text"].lower().strip() == section_name.lower():
            inside = True
            continue
        if inside:
            # stop at next section heading
            if b["style"] in ["Heading 1", "Heading 2", "Heading 3"] or (
                b["text"] in ["Experience", "Projects", "Education",
                               "Competencies", "Achievements & Certifications",
                               "Skills", "Summary"]
            ):
                break
            result.append(b["text"])
    return result


def parse_skills_line(line: str, prefix: str) -> list[str]:
    """Parse 'Programming Languages: Python, JS, ...' into a list."""
    if prefix in line:
        raw = line.replace(prefix, "").strip()
        # clean up parenthetical groups that got split by commas
        # e.g. "ABAP (CDS, RAP, OData)" stays together
        items = []
        current = ""
        depth = 0
        for char in raw:
            if char == "(":
                depth += 1
                current += char
            elif char == ")":
                depth -= 1
                current += char
            elif char == "," and depth == 0:
                if current.strip():
                    items.append(current.strip())
                current = ""
            else:
                current += char
        if current.strip():
            items.append(current.strip())
        return items
    return []


def parse_cv_from_docx(docx_path: str) -> dict:
    """
    Parse a .docx CV file into a structured dict.
    Works generically — doesn't assume exact paragraph indices.
    """
    doc    = Document(docx_path)
    blocks = extract_text_blocks(doc)
    texts  = [b["text"] for b in blocks]

    cv = {
        "name":       "",
        "title":      "",
        "location":   "",
        "summary":    "",
        "skills": {
            "programming_languages": [],
            "frameworks_libraries":  [],
            "databases":             [],
            "ai_ml":                 [],
            "cloud_devops":          [],
            "data_engineering":      []
        },
        "experience":     [],
        "projects":       [],
        "education":      [],
        "certifications": [],
        "github":         "",
        "preferred_job_titles": [],
        "preferred_location":   ""
    }

    # ── name + title (first two non-empty blocks) ─────────────────────────────
    if len(texts) > 0:
        cv["name"]  = texts[0].strip()
    if len(texts) > 1:
        cv["title"] = texts[1].strip()

    # ── summary (longest paragraph near the top, before Experience) ───────────
    for b in blocks[:15]:
        if len(b["text"]) > 100:
            cv["summary"] = b["text"]
            break

    # ── skills ────────────────────────────────────────────────────────────────
    skill_map = {
        "Programming Languages:": "programming_languages",
        "Frameworks & Libraries:": "frameworks_libraries",
        "Databases:":              "databases",
        "AI/ML:":                  "ai_ml",
        "Cloud and DevOps:":       "cloud_devops",
        "Data Engineering:":       "data_engineering",
    }

    for text in texts:
        for prefix, key in skill_map.items():
            if text.startswith(prefix):
                cv["skills"][key] = parse_skills_line(text, prefix)

    # ── github ────────────────────────────────────────────────────────────────
    for text in texts:
        if "github.com" in text.lower():
            # extract URL
            match = re.search(r'https?://github\.com/\S+', text)
            if match:
                cv["github"] = match.group(0)

    # ── experience ────────────────────────────────────────────────────────────
    # find experience section and parse role blocks
    exp_section = False
    current_exp = None

    for i, b in enumerate(blocks):
        t = b["text"]

        # detect Experience section start
        if t.lower() == "experience":
            exp_section = True
            continue

        # detect Experience section end
        if exp_section and t.lower() in ["projects", "competencies",
                                          "education", "skills",
                                          "achievements & certifications"]:
            if current_exp:
                cv["experience"].append(current_exp)
                current_exp = None
            exp_section = False
            continue

        if not exp_section:
            continue

        # detect a new role (contains a year pattern like 2022 or "Current")
        year_pattern = re.search(r'(20\d{2}|Current|current|Present|present)', t)
        if year_pattern and len(t) > 20 and b["style"] in ["Normal", "Heading 2"]:
            if current_exp:
                cv["experience"].append(current_exp)
            current_exp = {
                "role":        t,
                "company":     blocks[i+1]["text"] if i+1 < len(blocks) else "",
                "location":    blocks[i+1]["text"] if i+1 < len(blocks) else "",
                "period":      "",
                "bullets":     []
            }
        elif current_exp and b["style"] == "List Paragraph":
            current_exp["bullets"].append(t)

    if current_exp:
        cv["experience"].append(current_exp)

    # ── projects ──────────────────────────────────────────────────────────────
    proj_section = False
    current_proj = None

    for b in blocks:
        t = b["text"]

        if t.lower() == "projects":
            proj_section = True
            continue

        if proj_section and t.lower() in ["competencies", "education",
                                           "skills", "experience",
                                           "achievements & certifications"]:
            if current_proj:
                cv["projects"].append(current_proj)
                current_proj = None
            proj_section = False
            continue

        if not proj_section:
            continue

        # tech stack line (comma-separated technologies)
        if current_proj and "tech" not in current_proj and "," in t and len(t.split(",")) > 2:
            current_proj["tech"] = t
        elif current_proj and t.startswith("•"):
            current_proj["description"] = current_proj.get("description", "") + " " + t
        elif b["style"] == "Normal" and len(t) > 5:
            if current_proj:
                cv["projects"].append(current_proj)
            current_proj = {"name": t, "tech": "", "description": ""}

    if current_proj:
        cv["projects"].append(current_proj)

    # ── education ─────────────────────────────────────────────────────────────
    edu_section = False
    current_edu = None

    for b in blocks:
        t = b["text"]

        if t.lower() == "education":
            edu_section = True
            continue

        if edu_section and t.lower() in ["competencies", "projects",
                                          "skills", "experience",
                                          "achievements & certifications"]:
            if current_edu:
                cv["education"].append(current_edu)
                current_edu = None
            edu_section = False
            continue

        if not edu_section:
            continue

        year_pattern = re.search(r'(20\d{2}|present|Present)', t)
        if year_pattern and len(t) > 10:
            if current_edu:
                cv["education"].append(current_edu)
            current_edu = {
                "degree":         t,
                "university":     "",
                "period":         "",
                "grade":          "",
                "specialization": ""
            }
        elif current_edu:
            if "university" not in current_edu or not current_edu["university"]:
                current_edu["university"] = t
            elif b["style"] == "List Paragraph":
                current_edu["specialization"] = t

    if current_edu:
        cv["education"].append(current_edu)

    # ── certifications ────────────────────────────────────────────────────────
    cert_section = False
    for b in blocks:
        t = b["text"]
        if "achievements" in t.lower() or "certifications" in t.lower():
            cert_section = True
            continue
        if cert_section and b["style"] == "List Paragraph":
            cv["certifications"].append(t)

    # ── infer preferred job titles from title + experience ────────────────────
    title_lower = cv["title"].lower()
    titles = []
    if "ai" in title_lower or "ml" in title_lower:
        titles += ["AI Engineer", "ML Engineer", "AI/ML Engineer"]
    if "backend" in title_lower or "full stack" in title_lower:
        titles += ["Backend Developer", "Full Stack Developer"]
    if "devops" in title_lower or "platform" in title_lower:
        titles += ["DevOps Engineer", "Platform Engineer"]
    if "frontend" in title_lower:
        titles += ["Frontend Developer", "UI Developer"]
    if not titles:
        titles = ["Software Engineer", "Developer"]

    cv["preferred_job_titles"] = list(dict.fromkeys(titles))  # deduplicate

    # ── preferred location (default to Deutschland for now) ───────────────────
    for text in texts:
        if "deutschland" in text.lower() or "germany" in text.lower():
            cv["preferred_location"] = "Deutschland"
            break
    if not cv["preferred_location"]:
        cv["preferred_location"] = "Deutschland"

    return cv


def parse_and_save(docx_path: str, output_path: str) -> dict:
    """Parse CV and save to JSON file. Returns the cv dict."""
    cv = parse_cv_from_docx(docx_path)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(cv, f, indent=2, ensure_ascii=False)
    return cv


# ── test run ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "cv.docx"
    cv   = parse_and_save(path, "cv.json")
    print(f"✅ Parsed: {cv['name']} — {cv['title']}")
    print(f"   Skills: {sum(len(v) for v in cv['skills'].values())} total")
    print(f"   Experience: {len(cv['experience'])} roles")