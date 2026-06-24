"""Generate employees.csv with ~1000 rows across 3 tenants."""
import csv
import random
from datetime import date, timedelta

SEED = 42
random.seed(SEED)

TENANTS = ["acme", "beta", "gamma"]
DEPARTMENTS = ["Engineering", "Marketing", "Sales", "HR", "Finance"]
SALARY_RANGES = {
    "Engineering": (90_000, 180_000),
    "Marketing": (70_000, 130_000),
    "Sales": (65_000, 140_000),
    "HR": (60_000, 110_000),
    "Finance": (80_000, 150_000),
}
FIRST_NAMES = [
    "James", "Mary", "John", "Patricia", "Robert", "Jennifer", "Michael", "Linda",
    "William", "Barbara", "David", "Elizabeth", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Charles", "Karen", "Christopher", "Lisa", "Daniel", "Nancy",
    "Matthew", "Betty", "Anthony", "Margaret", "Mark", "Sandra", "Donald", "Ashley",
    "Steven", "Dorothy", "Paul", "Kimberly", "Andrew", "Emily", "Kenneth", "Donna",
    "Joshua", "Michelle", "Kevin", "Carol", "Brian", "Amanda", "George", "Melissa",
    "Timothy", "Deborah", "Ronald", "Stephanie", "Edward", "Rebecca", "Jason", "Sharon",
    "Jeffrey", "Laura", "Ryan", "Cynthia", "Jacob", "Kathleen", "Gary", "Amy",
    "Nicholas", "Angela", "Eric", "Shirley", "Jonathan", "Anna", "Stephen", "Brenda",
    "Larry", "Pamela", "Justin", "Emma", "Scott", "Nicole", "Brandon", "Helen",
    "Benjamin", "Samantha", "Samuel", "Katherine", "Raymond", "Christine", "Gregory",
    "Debra", "Frank", "Rachel", "Alexander", "Carolyn", "Patrick", "Janet",
]
LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
    "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker",
    "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores",
    "Green", "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell", "Mitchell",
    "Carter", "Roberts",
]
NOTES_TEMPLATES = [
    "Strong contributor, consistently meets deadlines.",
    "Excellent teamwork and communication skills.",
    "High performer with leadership potential.",
    "Meets expectations; opportunities for growth in Q3.",
    "Technical skills above average; working on soft skills.",
    "Reliable employee, handles pressure well.",
    "Creative problem-solver, valued by the team.",
    "Proactive in taking ownership of projects.",
    "Needs improvement in time management.",
    "Strong analytical mindset, great attention to detail.",
    "Quick learner, adapting well to new systems.",
    "Collaborative team player with positive attitude.",
    "Consistently delivers quality work on schedule.",
    "Shows initiative in cross-team projects.",
    "Strong candidate for senior role in next cycle.",
]


def random_date(start_year=2015, end_year=2024) -> str:
    start = date(start_year, 1, 1)
    end = date(end_year, 12, 31)
    delta = (end - start).days
    return (start + timedelta(days=random.randint(0, delta))).isoformat()


def generate_rows(n: int = 1000) -> list[dict]:
    rows = []
    for i in range(1, n + 1):
        tenant = TENANTS[i % len(TENANTS)]
        dept = random.choice(DEPARTMENTS)
        lo, hi = SALARY_RANGES[dept]
        salary = round(random.randint(lo, hi) / 1000) * 1000
        rows.append(
            {
                "user_id": i,
                "tenant_id": tenant,
                "name": f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}",
                "department": dept,
                "salary": salary,
                "performance_score": round(random.uniform(1.0, 5.0), 1),
                "hire_date": random_date(),
                "notes": random.choice(NOTES_TEMPLATES),
            }
        )
    return rows


def write_csv(path: str = "employees.csv", n: int = 1000) -> None:
    rows = generate_rows(n)
    fieldnames = ["user_id", "tenant_id", "name", "department", "salary",
                  "performance_score", "hire_date", "notes"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    counts = {}
    for r in rows:
        counts[r["tenant_id"]] = counts.get(r["tenant_id"], 0) + 1
    print(f"Wrote {len(rows)} rows to {path}")
    for t, c in sorted(counts.items()):
        print(f"  {t}: {c} rows")


if __name__ == "__main__":
    write_csv()
