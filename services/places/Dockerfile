FROM golang:1.22-bookworm AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o /out/places ./cmd/places

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /out/places /places
EXPOSE 8083
USER nonroot:nonroot
ENTRYPOINT ["/places"]
