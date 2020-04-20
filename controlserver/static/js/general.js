QueryString = {
	parse: function () {
		let qs = location.search.substring(1);
		if (!qs)
			return {};
		let vars = qs.split('&');
		let params = {};
		for (let i = 0; i < vars.length; i++) {
			let pair = vars[i].split('=');
			if (pair.length >= 2)
				params[pair[0]] = decodeURIComponent(pair[1]);
		}
		return params;
	},

	join: function (params) {
		let qs = [];
		for (key in params) {
			if (params.hasOwnProperty(key) && params[key] !== undefined)
				qs.push(key + '=' + encodeURIComponent(params[key]))
		}
		return '?' + qs.join('&');
	},

	update: function (changes) {
		let params = QueryString.parse();
		for (let key in changes) {
			if (changes.hasOwnProperty(key))
				params[key] = changes[key];
		}
		location.search = QueryString.join(params);
	}
};
