const app = angular.module('ControlServerApp', []);

app.controller('Packages2Controller', function ($scope, $http) {
	$scope.FLOWER_URL = FLOWER_URL;
	$scope.CHECKER_RESULT_URL = CHECKER_RESULT_URL.replace('123456789', '');

	$scope.messageList = [];
	$scope.deployAllUpdates = function () {
		$http.post('/packages/update', {}).then(function (xhr) {
			$scope.messageList.push(xhr.data.join('\n'));
		});
	};

	$scope.deployOne = function (serviceId) {
		if (!serviceId) return;
		$http.post('/packages/update', {service: serviceId}).then(function (xhr) {
			$scope.messageList.push(xhr.data.join('\n'));
		});
	};

	$scope.preloadAllCheckers = function () {
		$http.post('/packages/push', {}).then(function (xhr) {
			$scope.messageList.push(xhr.data);
		});
	};

    $scope.cloneAll = function () {
		$http.post('/scripts/service_update', {}).then(function (xhr) {
			$scope.messageList.push(xhr.data.join('\n'));
		}, function (xhr) {
			$scope.messageList.push(xhr.data.join('\n'));
        });
	};

	$scope.testResults = {};
	$scope.testScript = function (serviceId, teamId) {
		if (!teamId)
			return alert('Select team');
		$http.post('/packages/test', {service_id: serviceId, team_id: teamId}).then(function (xhr) {
			if (xhr.data) {
				xhr.data.time = Date.now();
                if (!$scope.testResults[serviceId])
                    $scope.testResults[serviceId] = [];
				$scope.testResults[serviceId].unshift(xhr.data);
			}
		});
	};
	$scope.testTeam = $('.team-select option[selected]').val();
});

