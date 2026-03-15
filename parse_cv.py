# ???????Doc parser??????
# from docx import Document
# def read_word_cv(file_path):
#     doc = Document(file_path)
    
#     # print all paragraphs in the document
#     for i, para in enumerate(doc.paragraphs):
#         if para.text.strip():  # Only print non-empty paragraphs
#             print(f"[{i}] style:'{para.style.name}' | text:'{para.text}'")
            
# read_word_cv("cv.docx")


import json
from docx import Document

def parse_cv(path):
    doc = Document(path)
    
    cv = {
        "name": "Mohith Tummala",
        "title": "AI/ML Engineer – Platform Engineering",
        "location": "St. Leon-Rot, Deutschland",
        "summary": "",
        "skills": {
            "programming_languages": [],
            "frameworks_libraries": [],
            "databases": [],
            "ai_ml": [],
            "cloud_devops": [],
            "data_engineering": []
        },
        "experience": [],
        "projects": [],
        "education": [],
        "certifications": [],
        "github": "https://github.com/DevMohith",
        "preferred_job_titles": [
            "AI Engineer",
            "ML Engineer", 
            "Backend Engineer",
            "Platform Engineer",
            "AI/ML Engineer"
        ],
        "preferred_location": "Deutschland"
    }

    paragraphs = [p for p in doc.paragraphs if p.text.strip()]

    # --- summary (index 6 in your output) ---
    cv["summary"] = paragraphs[2].text.strip()

    # --- skills (indices 37-42) ---
    for para in paragraphs:
        t = para.text.strip()
        if t.startswith("Programming Languages:"):
            cv["skills"]["programming_languages"] = [
                s.strip() for s in t.replace("Programming Languages:", "").split(",")
            ]
        elif t.startswith("Frameworks & Libraries:"):
            cv["skills"]["frameworks_libraries"] = [
                s.strip() for s in t.replace("Frameworks & Libraries:", "").split(",")
            ]
        elif t.startswith("Databases:"):
            cv["skills"]["databases"] = [
                s.strip() for s in t.replace("Databases:", "").split(",")
            ]
        elif t.startswith("AI/ML:"):
            cv["skills"]["ai_ml"] = [
                s.strip() for s in t.replace("AI/ML:", "").split(",")
            ]
        elif t.startswith("Cloud and DevOps:"):
            cv["skills"]["cloud_devops"] = [
                s.strip() for s in t.replace("Cloud and DevOps:", "").split(",")
            ]
        elif t.startswith("Data Engineering:"):
            cv["skills"]["data_engineering"] = [
                s.strip() for s in t.replace("Data Engineering:", "").split(",")
            ]

    # --- experience ---
    cv["experience"] = [
        {
            "role": "AI Engineer - Process AI Platform Engineering (Working Student)",
            "company": "SAP Signavio",
            "location": "St. Leon-Rot, Deutschland",
            "period": "09/2025–Current",
            "bullets": [
                paragraphs[i].text.strip()
                for i in range(len(paragraphs))
                if paragraphs[i].text.strip() in [
                    doc.paragraphs[10].text.strip(),
                    doc.paragraphs[11].text.strip(),
                    doc.paragraphs[12].text.strip(),
                    doc.paragraphs[13].text.strip(),
                ]
            ]
        },
        {
            "role": "Full Stack Developer - SAP CPIT (Working Student)",
            "company": "SAP SE",
            "location": "Walldorf, Deutschland",
            "period": "03/2025–09/2025",
            "bullets": [
                doc.paragraphs[16].text.strip(),
                doc.paragraphs[17].text.strip(),
                doc.paragraphs[18].text.strip(),
                doc.paragraphs[19].text.strip(),
            ]
        },
        {
            "role": "Junior DevOps Engineer",
            "company": "Diebold Nixdorf",
            "location": "Hyderabad, India",
            "period": "03/2022–05/2023",
            "bullets": [
                doc.paragraphs[23].text.strip(),
                doc.paragraphs[24].text.strip(),
                doc.paragraphs[25].text.strip(),
                doc.paragraphs[26].text.strip(),
            ]
        }
    ]

    # --- projects ---
    cv["projects"] = [
        {
            "name": "AI Workflow Orchestration Runtime Engine (Master Thesis)",
            "tech": doc.paragraphs[29].text.strip(),
            "description": doc.paragraphs[30].text.strip() + " " + doc.paragraphs[31].text.strip()
        },
        {
            "name": "Cloud-Native Kubernetes Autoscaling Backend System",
            "tech": doc.paragraphs[33].text.strip(),
            "description": doc.paragraphs[34].text.strip()
        }
    ]

    # --- education ---
    cv["education"] = [
        {
            "degree": "M.S. in Applied Computer Science",
            "university": "SRH University Heidelberg, Deutschland",
            "period": "04/2024–present",
            "grade": "1.7",
            "specialization": "Software Architecture and Artificial Intelligence"
        },
        {
            "degree": "Bachelor of Science in Computer Science",
            "university": "Osmania University Hyderabad, India",
            "period": "05/2018–09/2021",
            "grade": "8.25/10",
            "specialization": "Software Development with C++, LinuxOS and Machine Learning"
        }
    ]

    # --- certifications ---
    cv["certifications"] = [
        doc.paragraphs[53].text.strip(),
        doc.paragraphs[54].text.strip(),
        doc.paragraphs[55].text.strip(),
        doc.paragraphs[56].text.strip(),
        doc.paragraphs[57].text.strip(),
        doc.paragraphs[58].text.strip(),
        doc.paragraphs[59].text.strip(),
    ]

    return cv


if __name__ == "__main__":
    cv = parse_cv("cv.docx")
    with open("cv.json", "w", encoding="utf-8") as f:
        json.dump(cv, f, indent=2, ensure_ascii=False)
    print("✅ cv.json created successfully!")
    print(f"   Skills found: {sum(len(v) for v in cv['skills'].values())} total")
    print(f"   Experience entries: {len(cv['experience'])}")
    print(f"   Projects: {len(cv['projects'])}")
    print(f"   Certifications: {len(cv['certifications'])}")