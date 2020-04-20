import {async, ComponentFixture, TestBed} from '@angular/core/testing';

import {ScoretableComponent} from './scoretable.component';

describe('ScoretableComponent', () => {
	let component: ScoretableComponent;
	let fixture: ComponentFixture<ScoretableComponent>;

	beforeEach(async(() => {
		TestBed.configureTestingModule({
			declarations: [ScoretableComponent]
		})
			.compileComponents();
	}));

	beforeEach(() => {
		fixture = TestBed.createComponent(ScoretableComponent);
		component = fixture.componentInstance;
		fixture.detectChanges();
	});

	it('should create', () => {
		expect(component).toBeTruthy();
	});
});
