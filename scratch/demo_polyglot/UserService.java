package com.yunta.demo;

public class UserService {
    private String apiUrl;

    public UserService(String url) {
        this.apiUrl = url;
    }

    public String fetchUser(long userId) {
        return "User_" + userId;
    }
}
