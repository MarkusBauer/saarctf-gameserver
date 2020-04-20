$(function () {
	$('.filter_checkbox_list').submit(function (e) {
		e.preventDefault();
		e.stopPropagation();
		let items = '';
		for (let input of $(this).find('input[type=checkbox]')) {
			if (input.checked) {
				if (items !== '') items += '|';
				items += input.value;
			}
		}
		let update = {};
		update[$(this).data('param')] = items;
		QueryString.update(update);
	});

	$('.filter_options').change(function (e) {
		e.preventDefault();
		e.stopPropagation();
		let update = {};
		update[$(this).data('param')] = $(this).val() || undefined;
		QueryString.update(update);
	});

	$('.sort-link').click(function (e) {
		e.preventDefault();
		e.stopPropagation();
		let key = $(this).data('sort');
		let params = QueryString.parse();
		let order = params.sort === key ? (params.dir === 'desc' ? 'asc' : 'desc') : 'asc';
		QueryString.update({sort: key, dir: order});
	});
});
