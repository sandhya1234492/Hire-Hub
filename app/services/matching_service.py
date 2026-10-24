class MatchingService:
    def calculate(self, candidate, job):
        candidate_skills = {s.casefold() for s in candidate.get("skills", [])}
        required_skills = {s.casefold() for s in job.get("skills", [])}
        matched = candidate_skills & required_skills
        missing = required_skills - candidate_skills
        components = [len(matched) / len(required_skills) if required_skills else 1.0]
        years = float(candidate.get("experience_years", 0) or 0)
        minimum = float(job.get("experience_min", 0) or 0)
        maximum = float(job.get("experience_max", 0) or 0)
        components.append(1.0 if years >= minimum and (not maximum or years <= maximum) else 0.0)
        candidate_location = str(candidate.get("location", "")).casefold()
        job_location = str(job.get("location", "")).casefold()
        components.append(
            1.0 if job.get("work_mode") == "REMOTE" or not candidate_location
            or candidate_location in job_location or job_location in candidate_location else 0.0
        )
        expected_salary = candidate.get("expected_salary")
        max_salary = job.get("salary_max")
        components.append(
            1.0 if not expected_salary or not max_salary or float(expected_salary) <= float(max_salary)
            else 0.0
        )
        components.append(1.0 if job.get("work_mode") in {"REMOTE", "HYBRID", "ONSITE"} else 0.0)
        return {
            "score": round(sum(components) / len(components) * 100),
            "matched_skills": sorted(
                skill for skill in job.get("skills", []) if skill.casefold() in matched
            ),
            "missing_skills": sorted(
                skill for skill in job.get("skills", []) if skill.casefold() in missing
            ),
        }
