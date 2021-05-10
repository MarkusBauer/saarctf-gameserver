import {NgModule} from '@angular/core';
import {Routes, RouterModule} from '@angular/router';
import {PageNotFoundComponent} from "./page-not-found/page-not-found.component";
import {PageIndexComponent} from "./page-index/page-index.component";
import {PageTeamComponent} from "./page-team/page-team.component";

const routes: Routes = [
    {path: '', component: PageIndexComponent},
    {path: 'team/:teamid', component: PageTeamComponent},
    {path: '**', component: PageNotFoundComponent}
];

@NgModule({
    imports: [RouterModule.forRoot(routes, {
    initialNavigation: 'enabled',
    relativeLinkResolution: 'legacy'
})],
    exports: [RouterModule]
})
export class AppRoutingModule {
}
