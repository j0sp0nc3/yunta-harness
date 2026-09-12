pub struct Database {
    connection_string: String,
}

pub enum DbStatus {
    Connected,
    Disconnected,
}

impl Database {
    pub fn new(url: &str) -> Self {
        Database {
            connection_string: url.to_string(),
        }
    }

    pub fn status(&self) -> DbStatus {
        DbStatus::Connected
    }
}
