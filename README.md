# esphome-matter
ESPHome external component for matter support.

This is currently a work-in-progress and isn't usable yet... If you found this repo, come back later please :)

Do you like the idea of matter support in esphome? Give this project a star! Then I'll know people are interested.

# compilation

esphome-matter requires the esp-idf framework. The arduino framework won't work. Since esphome 2026.1.0 this is the
default anyway, but if you're still on an earlier version you need to specify the framework;

```yaml
esp32:
  framework:
    type: esp-idf
```