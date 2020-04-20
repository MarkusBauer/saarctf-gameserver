from __future__ import print_function
import random

lines = []
for r in range(1, 20):
	for i in range(100):
		lines.append('({}, {}, {}, {}, {}, now()),'.format(random.randint(1, 24), random.randint(1, 24), random.randint(1, 3), r+2, r))

with open('flags.sql', 'w') as f:
	f.write('\n'.join(lines))

