<?php
header('Content-Type: text/plain; charset=utf-8');

function getPath($team, $service, $round) {
	return '/dev/shm/storage/'.((int) $round).'_'.((int) $team).'_'.((int) $service).'.txt';
}

if (isset($_POST['team_id'])) {
	$path = getPath($_POST['team_id'], $_POST['service_id'], $_POST['round']);
	file_put_contents($path, $_POST['flag']."\n");
	echo '[OK]';
} elseif (isset($_GET['team_id'])) {
	$path = getPath($_GET['team_id'], $_GET['service_id'], $_GET['round']);
	if (file_exists($path)) {
		readfile($path);
	} else {
		echo 'File not found!';
	}
} else {
	echo "Welcome!\n";
	echo "- GET retrieves flags\n";
	echo "- POST stores flags\n";
}
