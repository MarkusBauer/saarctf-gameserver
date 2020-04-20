function MyGraph(element, series, title, options) {
	this.labels = [];
	this.data = [];
	this.datasets = [];
	for (let i = 0; i < series.length; i++) {
		this.data.push([]);
		this.datasets.push({label: series[i], data: this.data[i], cubicInterpolationMode: 'monotone'});
	}

	// default options
	options.title = {display: true, text: title};
	options.legend = {display: true, position: 'bottom'};
	if (options.scales === undefined) options.scales = {};
	if (options.scales.xAxes === undefined)
		options.scales.xAxes = [{
			type: 'time',
			time: {
				unit: 'minute',
				displayFormats: {minute: 'HH:mm'}
			}
		}];

	this.graph = {
		type: 'line',
		data: {datasets: this.datasets, labels: this.labels},
		options: options
	};
	this.graph.data.datasets[0].borderColor = 'rgba(151, 187, 205, 1)';
	this.graph.data.datasets[0].backgroundColor = 'rgba(151, 187, 205, 0.2)';
	this.chart = new Chart(element.getContext('2d'), this.graph);

	this.update = function () {
		this.chart.update();
	};
}
