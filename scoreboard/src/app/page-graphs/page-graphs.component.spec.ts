import {ComponentFixture, TestBed} from '@angular/core/testing';

import {PageGraphsComponent} from './page-graphs.component';

describe('PageGraphsComponent', () => {
    let component: PageGraphsComponent;
    let fixture: ComponentFixture<PageGraphsComponent>;

    beforeEach(async () => {
        await TestBed.configureTestingModule({
            declarations: [PageGraphsComponent]
        })
            .compileComponents();

        fixture = TestBed.createComponent(PageGraphsComponent);
        component = fixture.componentInstance;
        fixture.detectChanges();
    });

    it('should create', () => {
        expect(component).toBeTruthy();
    });
});
