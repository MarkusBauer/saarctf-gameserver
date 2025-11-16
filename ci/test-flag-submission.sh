#!/usr/bin/env bash
set -euxo pipefail

# shellcheck source=/dev/null
. venv/bin/activate

# Configure database credentials for container setup
cp ./ci-config.yaml ./config.yaml
export FLASK_APP=controlserver/app.py
alembic upgrade head
flask run --host=0.0.0.0 &
# Ensure flask is fully started by building something in the mean time

# Build flag submission server
mkdir flag-submission-server/build
pushd flag-submission-server/build
cmake -DCMAKE_BUILD_TYPE=Release -DPostgreSQL_ADDITIONAL_VERSIONS=17 ..
make
popd

# Run some simple start/stop tests against the gameserver
./ci/ctf.py start
sleep 3
./ci/ctf.py pause
sleep 3
./ci/ctf.py start
sleep 3
./ci/vpn.sh close
sleep 3
./ci/vpn.sh open
sleep 3
./ci/ctf.py stop
echo "yes" | python3 ./scripts/reset_ctf.py

# Start the gameserver and start the game
./ci/ctf.py start
# Test flag submitter
pushd flag-submission-server/build
./testsuite
./flag-submission-server > /tmp/submission.stdout 2>/tmp/submission.stderr &
# SUBMISSION_SERVER_PID=$!
sleep 1
./benchmark-newflags
./benchmark-oldflags
# Check response of flag submission
python3 ../scripts/submit_new_flags.py 10
killall ./flag-submission-server
echo "Submission Server Recorded Stdout:"
cat /tmp/submission.stdout
echo "Submission Server Recorded Stderr:"
cat /tmp/submission.stderr
popd
echo "yes" | python3 ./scripts/reset_ctf.py
