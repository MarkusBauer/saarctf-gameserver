const app = angular.module('ControlServerApp', []);

const CTFTimer = {
	STOPPED: 1,
	SUSPENDED: 2,
	RUNNING: 3
};

app.controller('PackagesController', function ($scope, $http) {
	$scope.FLOWER_URL = FLOWER_URL;
	$scope.CHECKER_RESULT_URL = CHECKER_RESULT_URL.replace('123456789', '');

	$scope.messageList = [];
	$scope.updateCheckers = function () {
		$http.post('/packages/update', {}).then(function (xhr) {
			$scope.messageList.push(xhr.data.join('\n'));
		});
	};

	$scope.updateSingleChecker = function (serviceId) {
		if (!serviceId) return;
		$http.post('/packages/update', {service: serviceId}).then(function (xhr) {
			$scope.messageList.push(xhr.data.join('\n'));
		});
	};

	$scope.pushPackages = function () {
		$http.post('/packages/push', {}).then(function (xhr) {
			$scope.messageList.push(xhr.data);
		});
	};

	$scope.commands = [];
	$scope.runCommands = function (command) {
		console.log(command);
		$http.post('/packages/run', {command: command}).then(function (xhr) {
			if (xhr.data) {
				$scope.commands.push({cmd: command, task: xhr.data});
			}
		});
	};

	$scope.testRound = '';
	$scope.testResults = [];
	$scope.testScript = function (serviceId, teamId, round) {
		if (!serviceId)
			return alert('Select service');
		if (!teamId)
			return alert('Select team');
		$http.post('/packages/test', {service_id: serviceId, team_id: teamId, round: round}).then(function (xhr) {
			if (xhr.data) {
				xhr.data.time = Date.now();
				$scope.testResults.push(xhr.data);
			}
		});
	};
	$scope.testTeam = $('.team-select option[selected]').val();
});

