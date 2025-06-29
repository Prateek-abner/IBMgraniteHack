

package com.example.api.test;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
public class PetStoreAPIApiTest {

    private WebTestClient webTestClient;

    @BeforeEach
    public void setup() {
        webTestClient = WebTestClient.bindToController(new PetStoreAPIController()).build();
    }

    @Test
    public void testListPets() {
        // Positive test case for valid input
        webTestClient.get().uri("/pets?limit=10")
                .exchange()
                .expectStatus().isOk()
                .expectBodyList(Pet.class)
                .hasSize(10);

        // Negative test case for invalid input
        webTestClient.get().uri("/pets?limit=abc")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    public void testCreatePet() {
        // Positive test case for valid input
        webTestClient.post().uri("/pets")
                .body(BodyInserters.fromObject(new Pet(1, "Dog", "Healthy")))
                .exchange()
                .expectStatus().isCreated();

        // Negative test case for invalid input
        webTestClient.post().uri("/pets")
                .body(BodyInserters.fromObject(new Pet(1, "Dog", null)))
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    public void testGetPetById() {
        // Positive test case for valid input
        webTestClient.get().uri("/pets/1")
                .exchange()
                .expectStatus().isOk()
                .expectBody(Pet.class)
                .isEqualTo(new Pet(1, "Dog", "Healthy"));

        // Negative test case for invalid input
        webTestClient.get().uri("/pets/abc")
                .exchange()
                .expectStatus().isBadRequest();
    }
}