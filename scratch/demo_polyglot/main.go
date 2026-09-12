package main

import "fmt"

type ServerConfig struct {
    Port int
}

func NewServerConfig(port int) *ServerConfig {
    return &ServerConfig{Port: port}
}

func (s *ServerConfig) Start() {
    fmt.Printf("Server starting on port %d\n", s.Port)
}
