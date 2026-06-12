"""
tests/test_cleaner.py — Unit tests for cleaning/cleaner.py
============================================================
Tests the core cleaning functions: fingerprinting, location standardization,
experience parsing, skill normalization, and job classification.
"""

import pytest
import sys
import os

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cleaning.cleaner import (
    make_fingerprint,
    standardize_location,
    parse_experience,
    normalize_skill,
    standardize_skills,
    strip_html,
    classify_job,
    clean_job,
)


# ═════════════════════════════════════════════════════════════
#  FINGERPRINT TESTS
# ═════════════════════════════════════════════════════════════

class TestMakeFingerprint:
    def test_basic_fingerprint(self):
        fp = make_fingerprint("Data Scientist", "Google", "Bangalore")
        assert isinstance(fp, str)
        assert len(fp) == 32  # MD5 hex digest

    def test_same_input_same_fingerprint(self):
        fp1 = make_fingerprint("ML Engineer", "Meta", "Mumbai")
        fp2 = make_fingerprint("ML Engineer", "Meta", "Mumbai")
        assert fp1 == fp2

    def test_case_insensitive(self):
        fp1 = make_fingerprint("Data Scientist", "Google", "Bangalore")
        fp2 = make_fingerprint("data scientist", "google", "bangalore")
        assert fp1 == fp2

    def test_different_titles_different_fingerprints(self):
        fp1 = make_fingerprint("Data Scientist", "Google", "Bangalore")
        fp2 = make_fingerprint("Data Engineer", "Google", "Bangalore")
        assert fp1 != fp2

    def test_source_job_id_differentiates(self):
        """Two companies same title+city but different source_job_id → different fingerprints."""
        fp1 = make_fingerprint("Data Analyst", "CompanyA", "Bangalore", source_job_id="123")
        fp2 = make_fingerprint("Data Analyst", "CompanyA", "Bangalore", source_job_id="456")
        assert fp1 != fp2

    def test_none_city_handled(self):
        fp = make_fingerprint("SDE", "Amazon", None)
        assert isinstance(fp, str) and len(fp) == 32

    def test_empty_strings(self):
        fp = make_fingerprint("", "", "")
        assert isinstance(fp, str)


# ═════════════════════════════════════════════════════════════
#  LOCATION TESTS
# ═════════════════════════════════════════════════════════════

class TestStandardizeLocation:
    def test_bangalore_variants(self):
        result = standardize_location(["Bengaluru"])
        assert result["city"] == "Bangalore"
        assert result["state"] == "Karnataka"
        assert result["country"] == "India"

    def test_bangalore_with_comma(self):
        result = standardize_location(["Bengaluru, Karnataka"])
        assert result["city"] == "Bangalore"

    def test_delhi_ncr(self):
        result = standardize_location(["Gurgaon"])
        assert result["city"] == "Delhi NCR"
        assert result["state"] == "Delhi"

    def test_remote_detection(self):
        result = standardize_location(["Remote", "Bangalore"])
        assert result["work_mode"] == "Remote"

    def test_hybrid_detection(self):
        result = standardize_location(["Hybrid", "Pune"])
        assert result["work_mode"] == "Hybrid"

    def test_onsite_default(self):
        result = standardize_location(["Chennai"])
        assert result["work_mode"] == "Onsite"

    def test_unknown_city_fallback(self):
        """Unknown cities should be title-cased rather than None."""
        result = standardize_location(["Siliguri"])
        assert result["city"] == "Siliguri"
        assert result["state"] is None  # not in CITY_TO_STATE

    def test_empty_list(self):
        result = standardize_location([])
        assert result["city"] is None
        assert result["work_mode"] == "Onsite"

    def test_expanded_city_thiruvananthapuram(self):
        result = standardize_location(["Thiruvananthapuram"])
        assert result["city"] == "Thiruvananthapuram"
        assert result["state"] == "Kerala"

    def test_expanded_city_mangalore(self):
        result = standardize_location(["Mangaluru"])
        assert result["city"] == "Mangalore"

    def test_raw_location_preserved(self):
        result = standardize_location(["Bengaluru", "Karnataka"])
        assert result["raw_location"] == "Bengaluru, Karnataka"

    def test_pan_india_not_used_as_city(self):
        """Pan India should not be set as city — only generic values."""
        result = standardize_location(["Pan India"])
        # Should be None since Pan India is excluded from city candidates
        assert result["city"] is None or result["city"] != "Pan India"


# ═════════════════════════════════════════════════════════════
#  EXPERIENCE TESTS
# ═════════════════════════════════════════════════════════════

class TestParseExperience:
    def test_integer_inputs(self):
        result = parse_experience(2, 5)
        assert result["min_exp"] == 2
        assert result["max_exp"] == 5
        assert result["raw_experience"] == "2-5 Yrs"

    def test_none_inputs(self):
        result = parse_experience(None, None)
        assert result["min_exp"] is None
        assert result["max_exp"] is None
        assert result["raw_experience"] is None

    def test_min_only(self):
        result = parse_experience(3, None)
        assert result["min_exp"] == 3
        assert result["max_exp"] is None
        assert result["raw_experience"] == "3+ Yrs"

    def test_negative_clamped(self):
        result = parse_experience(-1, 5)
        assert result["min_exp"] == 0  # clamped

    def test_float_input(self):
        result = parse_experience(2.5, 7.0)
        assert result["min_exp"] == 2
        assert result["max_exp"] == 7


# ═════════════════════════════════════════════════════════════
#  SKILL NORMALIZATION TESTS
# ═════════════════════════════════════════════════════════════

class TestNormalizeSkill:
    def test_python_alias(self):
        assert normalize_skill("Python3") == "python"
        assert normalize_skill("python programming") == "python"

    def test_ml_alias(self):
        assert normalize_skill("ML") == "machine learning"
        assert normalize_skill("machine-learning") == "machine learning"

    def test_cloud_aliases(self):
        assert normalize_skill("Amazon Web Services") == "aws"
        assert normalize_skill("Google Cloud Platform") == "gcp"
        assert normalize_skill("Microsoft Azure") == "azure"

    def test_modern_ai_tools(self):
        assert normalize_skill("Hugging Face") == "huggingface"
        assert normalize_skill("LangChain") == "langchain"
        assert normalize_skill("OpenAI") == "openai"
        assert normalize_skill("Vertex AI") == "vertex ai"

    def test_empty_skill(self):
        assert normalize_skill("") == ""
        assert normalize_skill(None) == ""

    def test_unknown_skill_passthrough(self):
        assert normalize_skill("SomeNewFramework") == "somenewframework"


class TestStandardizeSkills:
    def test_deduplication(self):
        result = standardize_skills(["Python", "python3", "Python Programming"])
        assert len(result["standardized_skills"]) == 1
        assert result["standardized_skills"][0] == "python"

    def test_raw_preserved(self):
        result = standardize_skills(["Python", "TensorFlow"])
        assert result["raw_skills"] == ["Python", "TensorFlow"]

    def test_empty_input(self):
        result = standardize_skills([])
        assert result["raw_skills"] == []
        assert result["standardized_skills"] == []


# ═════════════════════════════════════════════════════════════
#  HTML STRIPPING TESTS
# ═════════════════════════════════════════════════════════════

class TestStripHtml:
    def test_basic_html(self):
        result = strip_html("<p>Hello <b>World</b></p>")
        assert "Hello" in result
        assert "World" in result
        assert "<" not in result

    def test_script_removal(self):
        result = strip_html("<script>alert('xss')</script>Normal text")
        assert "alert" not in result
        assert "Normal text" in result

    def test_empty_input(self):
        assert strip_html("") == ""
        assert strip_html(None) == ""

    def test_entities_decoded(self):
        result = strip_html("AT&amp;T &lt;company&gt;")
        assert "AT&T" in result


# ═════════════════════════════════════════════════════════════
#  JOB CLASSIFICATION TESTS
# ═════════════════════════════════════════════════════════════

class TestClassifyJob:
    def test_data_scientist(self):
        result = classify_job("Senior Data Scientist")
        assert result["job_category"] == "Data Science"
        assert result["job_field"] == "Data"
        assert result["job_sub_field"] == "Data Science"

    def test_ml_engineer(self):
        result = classify_job("Machine Learning Engineer")
        assert result["job_field"] == "AI / ML"
        assert result["job_sub_field"] == "Machine Learning"

    def test_genai(self):
        result = classify_job("GenAI Platform Lead")
        assert result["job_field"] == "AI / ML"
        assert result["job_sub_field"] == "Generative AI"

    def test_sales(self):
        result = classify_job("Regional Sales Manager")
        assert result["job_field"] == "Sales & Marketing"
        assert result["job_sub_field"] == "Sales & BD"

    def test_unknown_title_description_fallback(self):
        """When title doesn't match, should fall back to description."""
        result = classify_job(
            "Senior Consultant",
            description="Working on machine learning models and deep learning pipelines"
        )
        assert result["job_field"] == "AI / ML"
        assert result["job_category"] == "Machine Learning"

    def test_unknown_both(self):
        result = classify_job("Executive Assistant")
        assert result["job_field"] == "Other"
        assert result["job_category"] == "Other"


# ═════════════════════════════════════════════════════════════
#  CLEAN_JOB INTEGRATION TEST
# ═════════════════════════════════════════════════════════════

class TestCleanJob:
    def test_full_pipeline(self):
        raw = {
            "source": "foundit",
            "source_job_id": "12345",
            "title": "Data Scientist",
            "company": "Google",
            "locations": ["Bangalore", "Karnataka"],
            "skills": ["Python", "ML", "TensorFlow"],
            "min_experience": 2,
            "max_experience": 5,
            "min_salary": 1500000,
            "max_salary": 2500000,
            "salary_currency": "INR",
            "description": "<p>Join our <b>AI</b> team</p>",
            "job_url": "https://example.com/job/12345",
            "posted_at": "2025-06-01T00:00:00+00:00",
        }

        result = clean_job(raw, search_keyword="data scientist")

        # Fingerprint
        assert len(result["fingerprint"]) == 32

        # Location
        assert result["city"] == "Bangalore"
        assert result["state"] == "Karnataka"
        assert result["work_mode"] == "Onsite"

        # Experience
        assert result["min_exp"] == 2
        assert result["max_exp"] == 5

        # Skills
        assert "python" in result["standardized_skills"]
        assert "machine learning" in result["standardized_skills"]
        assert "tensorflow" in result["standardized_skills"]

        # Category (two-level)
        assert result["job_field"] == "Data"
        assert result["job_sub_field"] == "Data Science"
        assert result["job_category"] == "Data Science"

        # Description cleaned
        assert "<" not in result["description"]
        assert "AI" in result["description"]

        # Search keyword tagged
        assert "data scientist" in result["search_keywords"]

        # Staleness fields
        assert result["is_active"] is True
