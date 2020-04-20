import {async, ComponentFixture, TestBed} from '@angular/core/testing';

import {CurrentTickComponent} from './current-tick.component';

describe('CurrentTickComponent', () => {
	let component: CurrentTickComponent;
	let fixture: ComponentFixture<CurrentTickComponent>;

	beforeEach(async(() => {
		TestBed.configureTestingModule({
			declarations: [CurrentTickComponent]
		})
			.compileComponents();
	}));

	beforeEach(() => {
		fixture = TestBed.createComponent(CurrentTickComponent);
		component = fixture.componentInstance;
		fixture.detectChanges();
	});

	it('should create', () => {
		expect(component).toBeTruthy();
	});
});
