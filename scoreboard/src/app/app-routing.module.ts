import {NgModule} from '@angular/core';
import {Routes, RouterModule} from '@angular/router';
import {PageNotFoundComponent} from "./page-not-found/page-not-found.component";
import {PageIndexComponent} from "./page-index/page-index.component";
import {PageTeamComponent} from "./page-team/page-team.component";
import {PageGraphsComponent} from "./page-graphs/page-graphs.component";

const routes: Routes = [
    {path: '', component: PageIndexComponent},
    {path: 'team/:teamid', component: PageTeamComponent},
    {path: 'graphs', component: PageGraphsComponent},
    {path: '**', component: PageNotFoundComponent}
];

@NgModule({
    imports: [RouterModule.forRoot(routes, {
    initialNavigation: 'enabledBlocking'
})],
    exports: [RouterModule]
})
export class AppRoutingModule {
}
