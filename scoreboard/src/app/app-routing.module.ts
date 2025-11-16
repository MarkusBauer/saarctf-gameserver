import {NgModule} from "@angular/core";
import {Routes, RouterModule} from "@angular/router";
import {PageNotFoundComponent} from "./page-not-found/page-not-found.component";
import {PageIndexComponent} from "./page-index/page-index.component";
import {PageTeamComponent} from "./page-team/page-team.component";
import {PageGraphsComponent} from "./page-graphs/page-graphs.component";
import {environment} from "../environments/environment";
import {PageDashboardComponent} from "./page-dashboard/page-dashboard.component";

const routes: Routes = [
    {path: "", component: PageIndexComponent, title: environment.ctf_name + ' Scoreboard'},
    {path: "dashboard", component: PageDashboardComponent, title: environment.ctf_name + ' Scoreboard'},
    {path: "team/:teamid", component: PageTeamComponent, title: 'Team | ' + environment.ctf_name + ' Scoreboard'},
    {path: "graphs", component: PageGraphsComponent, title: 'Graphs | ' + environment.ctf_name + ' Scoreboard'},
    {path: "**", component: PageNotFoundComponent, title: 'Not found | ' + environment.ctf_name + ' Scoreboard'},
];

@NgModule({
    imports: [
        RouterModule.forRoot(routes, {
            initialNavigation: "enabledBlocking",
        }),
    ],
    exports: [RouterModule],
})
export class AppRoutingModule {
}
