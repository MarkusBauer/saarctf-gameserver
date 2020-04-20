const app = angular.module('ControlServerApp', ['chart.js']);

const DATE_FORMAT = 'DD.MM.YYYY HH:mm:00';

app.filter('newDate', function () {
	return function (item) {
		if (typeof item === 'number')
			item *= 1000;
		return new Date(item);
	};
});

app.filter('interval', function () {
	return function (item) {
		return moment.duration(item, 'seconds').format();
	};
});

app.directive('bsDatepicker', function ($timeout, $parse) {
	return {
		link: function ($scope, element, $attrs) {
			return $timeout(function () {
				const ngModelGetter = $parse($attrs['ngModel']);
				let parent = $(element).parent('.input-group.date');
				return $(parent.length ? parent : element).datetimepicker({
					format: DATE_FORMAT
				}).on('dp.change', function (event) {
					$scope.$apply(function () {
						return ngModelGetter.assign($scope, $(element).val());
					});
				});
			});
		}
	};
});


const CTFTimer = {
	STOPPED: 1,
	SUSPENDED: 2,
	RUNNING: 3
};

app.controller('TimingController', function ($scope, $http) {
	$scope.timer = {
		state: CTFTimer.STOPPED,
		desiredState: CTFTimer.STOPPED,
		currentRound: 0,
		roundStart: null,
		roundEnd: null,
		roundTime: 0,
		serverTime: 0,
		masterTimers: 0,
		startAt: null,
		lastRound: null
	};
	$scope.CTFTimer = CTFTimer;

	$scope.updateTimingInformation = function () {
		$http.get('/overview/timing').then(function (xhr) {
			$scope.timer = xhr.data;
			if (!$scope.newroundtime)
				$scope.newroundtime = $scope.timer.roundTime;
			if ($scope.timer.lastRound) {
				if ($scope.timer.state === CTFTimer.RUNNING) {
					$scope.timer.endAt = $scope.timer.roundEnd + $scope.timer.roundTime * ($scope.timer.lastRound - $scope.timer.currentRound);
				} else if ($scope.timer.startAt) {
					$scope.timer.endAt = $scope.timer.startAt + $scope.timer.roundTime * ($scope.timer.lastRound - $scope.timer.currentRound);
				}
			}
		});
	};

	$scope.setState = function (state) {
		$http.post('/overview/set_timing', {"state": state}).then($scope.updateTimingInformation);
	};

	$scope.setRoundTime = function (roundtime) {
		$http.post('/overview/set_timing', {"roundtime": roundtime}).then($scope.updateTimingInformation);
	};

	$scope.setLastRound = function (lastRound) {
		$http.post('/overview/set_timing', {"lastround": lastRound}).then($scope.updateTimingInformation);
	};

	$scope.setAutostart = function (autostart) {
		if (typeof autostart === 'string') {
			autostart = moment(autostart, DATE_FORMAT).unix();
		}
		$http.post('/overview/set_timing', {"startAt": autostart}).then($scope.updateTimingInformation);
	};

	setInterval($scope.updateTimingInformation, 30 * 1000);
	setInterval(function () {
		$scope.$apply(function () {
			$scope.timer.serverTime++;
			if ($scope.timer.serverTime === $scope.timer.roundEnd + 1 || $scope.timer.serverTime === $scope.timer.startAt + 1)
				$scope.updateTimingInformation();
		});
	}, 1000);
	$scope.updateTimingInformation();
});


app.controller('LogController', function ($scope, $http) {
	$scope.logs = [];
	$scope.LogLevel = {
		DEBUG: 1,
		INFO: 5,
		IMPORTANT: 10,
		NOTIFICATION: 15,
		WARNING: 20,
		ERROR: 30
	};
	$scope.maxId = 0;

	function newLogs(logs) {
		var entry = null;
		var count = 0;
		var msgPrefix = '';

		for (let log of logs) {
			if (log.level >= $scope.LogLevel.NOTIFICATION) {
				count++;
				if (!entry) entry = log;
				if (log.level >= $scope.LogLevel.ERROR)
					msgPrefix = 'ERROR: ';
				else if (log.level >= $scope.LogLevel.WARNING && !msgPrefix)
					msgPrefix = 'WARNING: ';
			}
		}

		if (count > 0 && (localStorage.getItem('dashboard:lastLogNotification') || 0) < entry.id) {
			localStorage.setItem('dashboard:lastLogNotification', entry.id);
			if (Notification.permission !== "granted")
				Notification.requestPermission();
			let notification = new Notification('saarCTF', {
				body: msgPrefix + entry.title + '  (click to view)',
				dir: 'auto'
			});
			notification.onclick = function () {
				let w = window.open(location.href + 'log_messages/view/' + entry.id, '_blank');
				w.focus();
			};
		}
	}


	$scope.updateLogs = function () {
		if ($scope.maxId) {
			$http.get('/overview/logs/' + $scope.maxId).then(function (xhr) {
				$scope.logs = xhr.data.concat($scope.logs);
				if ($scope.logs.length > 100)
					$scope.logs = $scope.logs.slice(0, 100);
				if ($scope.logs.length > 0)
					$scope.maxId = $scope.logs[0].id;
				newLogs(xhr.data);
			});
		} else {
			$http.get('/overview/logs').then(function (xhr) {
				$scope.logs = xhr.data;
				if ($scope.logs.length > 0)
					$scope.maxId = $scope.logs[0].id;
				newLogs(xhr.data);
			});
		}
	};

	setInterval($scope.updateLogs, 9 * 1000);
	$scope.updateLogs();

	if (Notification.permission !== "granted")
		Notification.requestPermission();
});


app.controller('ComponentsController', function ($scope, $http) {
	$scope.redis = [];
	$scope.redis_offline = [];
	$scope.redis_stats = {};
	$scope.redis_combined = {};

	function components_combine(list) {
		let combined = {};
		for (let client of list) {
			let key = client.name + ' | ' + client.addr + ' | ' + client.cmd;
			if (combined[key]) {
				combined[key].combine_count++;
			} else {
				combined[key] = client;
				client.combine_count = 1;
			}
		}
		// console.log(combined, list);
		return combined;
	}

	$scope.updateComponents = function () {
		$http.get('/overview/components').then(function (xhr) {
			let ids = {};
			$scope.redis_stats = {};
			for (let client of xhr.data.redis) {
				ids[client.id] = true;
				client.addr = client.addr.split(':')[0];
				$scope.redis_stats[client.name] = ($scope.redis_stats[client.name] || 0) + 1;
			}
			let disconnectedThings = new Set();
			for (let client of $scope.redis) {
				if (!ids[client.id] && client.name && !client.name.startsWith('script-')) {
					//TODO remove from this list after some time
					$scope.redis_offline.push(client);
					disconnectedThings.add(client.name || '(unnamed)');
				}
			}
			if (disconnectedThings.size === 1) {
				let notification = new Notification('saarCTF', {
					body: 'Warning: ' + Array.from(disconnectedThings)[0] + ' disconnected from the Redis server.',
					dir: 'auto'
				});
			} else if (disconnectedThings.size > 1) {
				let notification = new Notification('saarCTF', {
					body: 'Warning: ' + disconnectedThings.size + ' things disconnected from the Redis server: ' + Array.from(disconnectedThings).join(', '),
					dir: 'auto'
				});
			}
			$scope.redis = xhr.data.redis;
			$scope.redis_combined = components_combine($scope.redis);
		});
	};

	setInterval($scope.updateComponents, 19 * 1000);
	$scope.updateComponents();
});


app.controller('VPNController', function ($scope, $http) {
	$scope.state = false;
	$scope.banned = [];
	$scope.bantick = null;
	$scope.banteam = null;
	$scope.teams_online = 0;
	$scope.teams_online_once = 0;
	$scope.teams_offline = 0;

	$scope.traffic_last = 0;

	var axesMB = {
		yAxes: [{
			ticks: {
				callback: function (value, index, values) {
					return (Math.round(value / 1000) / 1000.0).toLocaleString('en-EN').replace(',', ' ') + ' MB';
				}
			}
		}]
	};

	function createGraphs() {
		if (!$scope.graph_bytes)
			$scope.graph_bytes = new MyGraph(document.getElementById('graph1'), ["team's download", "team's upload"],
				'VPN traffic stats (traffic per minute)', {scales: axesMB});
		if (!$scope.graph_bytes_2)
			$scope.graph_bytes_2 = new MyGraph(document.getElementById('graph2'), ["team to team", "total"],
				'VPN traffic stats (traffic per minute)', {scales: axesMB});
		if (!$scope.graph_connections)
			$scope.graph_connections = new MyGraph(document.getElementById('graph3'), ["team to team", "total"],
				'VPN connections (SYNs)', {});
	}

	$scope.updateComponents = function () {
		$http.get('/overview/vpn', {params: {last: $scope.traffic_last}}).then(function (xhr) {
			$scope.state = xhr.data.state;
			$scope.banned = xhr.data.banned;
			$scope.teams_online = xhr.data.teams_online;
			$scope.teams_online_once = xhr.data.teams_online_once;
			$scope.teams_offline = xhr.data.teams_offline;

			if (xhr.data.traffic_stats.length > 0) {
				createGraphs();
				// format: dt_bytes, dt_syns, dg_bytes, dg_syns, ut_bytes, ut_syns, ug_bytes, ug_syns
				for (var i = 0; i < xhr.data.traffic_stats.length; i++) {
					if (xhr.data.traffic_stats_keys[i] > $scope.traffic_last) {
						var datapoint = xhr.data.traffic_stats[i];
						var time = new Date(xhr.data.traffic_stats_keys[i] * 1000);
						$scope.graph_bytes.labels.push(time);
						$scope.graph_bytes_2.labels.push(time);
						$scope.graph_connections.labels.push(time);
						$scope.graph_bytes.data[0].push(datapoint[0] + datapoint[2]);
						$scope.graph_bytes.data[1].push(datapoint[4] + datapoint[6]);
						$scope.graph_bytes_2.data[0].push(datapoint[0] + datapoint[4]);
						$scope.graph_bytes_2.data[1].push(datapoint[0] + datapoint[4] + datapoint[2] + datapoint[6]);
						$scope.graph_connections.data[0].push(datapoint[1] + datapoint[5]);
						$scope.graph_connections.data[1].push(datapoint[1] + datapoint[5] + datapoint[3] + datapoint[7]);

						if ($scope.graph_bytes.data[0].length > 60) {
							$scope.graph_bytes.data[0].shift();
							$scope.graph_bytes.data[1].shift();
							$scope.graph_bytes.labels.shift();
						}
						if ($scope.graph_bytes_2.data[0].length > 60) {
							$scope.graph_bytes_2.data[0].shift();
							$scope.graph_bytes_2.data[1].shift();
							$scope.graph_bytes_2.labels.shift();
						}
						if ($scope.graph_connections.data[0].length > 60) {
							$scope.graph_connections.data[0].shift();
							$scope.graph_connections.data[1].shift();
							$scope.graph_connections.labels.shift();
						}

						$scope.traffic_last = xhr.data.traffic_stats_keys[i];
					}
				}
				$scope.graph_bytes.update();
				$scope.graph_bytes_2.update();
				$scope.graph_connections.update();
			}
		});
	};

	$scope.setState = function (state) {
		$http.post('/overview/set_vpn', {state: state}).then($scope.updateComponents);
	};

	$scope.ban = function (id, tick) {
		if (!id) return;
		if (confirm('Really ban team #' + id + '?')) {
			$http.post('/overview/set_vpn', {ban: {team_id: id, tick: tick}}).then($scope.updateComponents);
		}
	};

	$scope.unban = function (id) {
		$http.post('/overview/set_vpn', {unban: id}).then($scope.updateComponents);
	};

	setInterval($scope.updateComponents, 28 * 1000);
	$scope.updateComponents();
});


app.controller('FlowerController', function ($scope, $http) {
	var url = document.getElementById('flower-url').dataset['value'];
	$scope.workers = [];
	$scope.online = 0;
	$scope.connected = false;

	$scope.concurrency = {};
	$scope.needConcurrencyUpdate = true;

	$scope.updateComponents = function () {
		$http.get(url + '?json=1').then(function (xhr) {
			$scope.workers = xhr.data.data;
			$scope.connected = true;
			$scope.online = 0;
			for (var i = 0; i < $scope.workers.length; i++) {
				if ($scope.workers[i].status)
					$scope.online++;
				if ($scope.concurrency[$scope.workers[i].hostname] === undefined)
					$scope.needConcurrencyUpdate = true;
			}
		});
	};
	$scope.updateConcurrency = function () {
		$http.get(url + 'api/workers?refresh=1').then(function (xhr) {
			$scope.concurrency = {};
			for (var name in xhr.data) {
				if (xhr.data.hasOwnProperty(name) && xhr.data[name].stats) {
					$scope.concurrency[name] = xhr.data[name].stats.pool.processes.length;
				}
			}
			$scope.needConcurrencyUpdate = false;
		}, function (x) {
			console.error(x);
		});
	};
	setInterval($scope.updateComponents, 45 * 1000);
	setInterval($scope.updateConcurrency, 53 * 1000);
	setInterval(function () {
		$scope.needConcurrencyUpdate = true;
	}, 10 * 60 * 1000);
	$scope.updateComponents();
	$scope.updateConcurrency();
});


app.controller('LayoutController', function ($rootScope) {
	$rootScope.hideControls = window.location.search.indexOf('nocontrol=1') !== -1;
	$rootScope.setHideControls = function (x) {
		$rootScope.hideControls = x;
	};
	$rootScope.notificationsAllowed = Notification.permission === 'granted';
	$rootScope.enableNotifications = function () {
		if (Notification.permission !== 'granted') {
			Notification.requestPermission().then(function () {
				$rootScope.$apply(function () {
					$rootScope.notificationsAllowed = Notification.permission === 'granted';
				});
			});
		}
	};
});
