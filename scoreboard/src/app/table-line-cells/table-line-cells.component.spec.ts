import { ComponentFixture, TestBed } from '@angular/core/testing';

import { TableLineCellsComponent } from './table-line-cells.component';

describe('TableLineCellsComponent', () => {
  let component: TableLineCellsComponent;
  let fixture: ComponentFixture<TableLineCellsComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      declarations: [ TableLineCellsComponent ]
    })
    .compileComponents();
  });

  beforeEach(() => {
    fixture = TestBed.createComponent(TableLineCellsComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
