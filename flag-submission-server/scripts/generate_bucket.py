import sys

from generate_flag import generate_flag

"""
USAGE: python3 generate_bucket.py <count>
Generates <count> new and valid flags, and saves them to ./bucket.txt
"""

BUCKET = int(sys.argv[1])

bucket = "".join(
    [generate_flag(i % 100 + 5, ((3 * i) % 8) + 1) + "\n" for i in range(BUCKET)]
)

with open("bucket.txt", "w") as f:
    f.write(bucket)

print(f"Bucket with {BUCKET} flags generated")
