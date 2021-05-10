import { ComponentFixture, TestBed } from '@angular/core/testing';

import { TableServiceHeaderCellComponent } from './table-service-header-cell.component';

describe('TableServiceHeaderCellComponent', () => {
  let component: TableServiceHeaderCellComponent;
  let fixture: ComponentFixture<TableServiceHeaderCellComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      declarations: [ TableServiceHeaderCellComponent ]
    })
    .compileComponents();
  });

  beforeEach(() => {
    fixture = TestBed.createComponent(TableServiceHeaderCellComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
