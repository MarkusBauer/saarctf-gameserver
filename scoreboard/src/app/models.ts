export interface Service {
    name: string;
    attackers: number;
    victims: number;
    first_blood: Array<string>;
    flag_stores: number;
    flag_stores_exploited: number;
}

export interface Team {
    id: number;  // set in backend service, not by the API
    name: string;
    vulnbox: string;
    aff: string;
    web: string;
    logo: string;
}

export interface ServiceResult {
    o: number; // off_points
    d: number; // def_points
    s: number; // sla_points
    do: number; // delta off_points
    dd: number; // delta def_points
    ds: number; // delta sla_points
    st: number; // stolen
    cap: number; // captured
    dst: number; // delta stolen
    dcap: number; // delta captured
    c: string; // checker status
    dc: Array<string>; // old checker results (round-1, -2, -3, ...)
    m: string | null; // checker message
}

export interface Rank {
    team_id: number;
    rank: number;
    points: number;
    o: number; // off_points
    d: number; // def_points
    s: number; // sla_points
    do: number;
    dd: number;
    ds: number;
    services: Array<ServiceResult>;
}

export interface RoundInformation {
    tick: number;
    services: Array<Service>;
    scoreboard: Array<Rank>;
}

export interface TeamHistoryInformation {
    services: Array<Service>;
    points: number[][];  // [service number => [tick => points]]
}

export interface ServiceStat {
    a: number;  // attackers
    v: number;  // victims
}

export interface ServiceStatsInformation {
    services: Array<Service>;
    stats: ServiceStat[][];  // [service number => [tick => stats]]
}
